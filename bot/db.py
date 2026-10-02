"""Хранилище на SQLite.

Бот обслуживает одну рабочую группу и работает одним процессом, поэтому
отдельный сервер базы не нужен: файл SQLite переживает перезапуск и
копируется обычным ``cp``.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY,
    first_name      TEXT NOT NULL DEFAULT '',
    last_name       TEXT NOT NULL DEFAULT '',
    username        TEXT,
    lang            TEXT,
    captcha_passed  INTEGER NOT NULL DEFAULT 0,
    banned          INTEGER NOT NULL DEFAULT 0,
    ban_reason      TEXT,
    blocked_bot     INTEGER NOT NULL DEFAULT 0,
    created_at      INTEGER NOT NULL,
    last_seen       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS users_last_seen ON users(last_seen);

-- сообщение в группе -> пользователь и его исходное сообщение
CREATE TABLE IF NOT EXISTS group_map (
    group_id     INTEGER NOT NULL,
    group_msg_id INTEGER NOT NULL,
    user_id      INTEGER NOT NULL,
    user_msg_id  INTEGER,
    PRIMARY KEY (group_id, group_msg_id)
);

-- ответ, доставленный пользователю -> сообщение сотрудника в группе
CREATE TABLE IF NOT EXISTS user_map (
    user_id      INTEGER NOT NULL,
    user_msg_id  INTEGER NOT NULL,
    group_id     INTEGER NOT NULL,
    group_msg_id INTEGER NOT NULL,
    PRIMARY KEY (user_id, user_msg_id)
);

CREATE TABLE IF NOT EXISTS admins (
    id         INTEGER PRIMARY KEY,
    added_by   INTEGER,
    added_at   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass
class User:
    id: int
    first_name: str
    last_name: str
    username: str | None
    lang: str | None
    captcha_passed: bool
    banned: bool
    ban_reason: str | None
    blocked_bot: bool
    created_at: int
    last_seen: int

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.first_name, self.last_name) if p) or str(self.id)


def _now() -> int:
    return int(time.time())


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self._conn is not None, "база не подключена"
        return self._conn

    async def _write(self, sql: str, params: tuple = ()) -> int:
        cur = await self.conn.execute(sql, params)
        await self.conn.commit()
        return cur.rowcount

    # ---- пользователи -------------------------------------------------

    async def touch_user(
        self,
        user_id: int,
        first_name: str,
        last_name: str | None,
        username: str | None,
        lang: str | None,
    ) -> tuple[User, bool]:
        """Создать или обновить пользователя. Возвращает (пользователь, новый ли)."""
        now = _now()
        cur = await self.conn.execute(
            "INSERT OR IGNORE INTO users (id, first_name, last_name, username, lang,"
            " created_at, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, first_name or "", last_name or "", username, lang, now, now),
        )
        created = cur.rowcount == 1
        if not created:
            await self.conn.execute(
                "UPDATE users SET first_name=?, last_name=?, username=?, lang=?,"
                " last_seen=?, blocked_bot=0 WHERE id=?",
                (first_name or "", last_name or "", username, lang, now, user_id),
            )
        await self.conn.commit()
        user = await self.get_user(user_id)
        assert user is not None
        return user, created

    async def get_user(self, user_id: int) -> User | None:
        cur = await self.conn.execute("SELECT * FROM users WHERE id=?", (user_id,))
        row = await cur.fetchone()
        if row is None:
            return None
        data = dict(row)
        for key in ("captcha_passed", "banned", "blocked_bot"):
            data[key] = bool(data[key])
        return User(**data)

    async def find_user_by_username(self, username: str) -> User | None:
        cur = await self.conn.execute(
            "SELECT id FROM users WHERE lower(username)=lower(?)", (username.lstrip("@"),)
        )
        row = await cur.fetchone()
        return await self.get_user(row["id"]) if row else None

    async def set_captcha_passed(self, user_id: int) -> None:
        await self._write("UPDATE users SET captcha_passed=1 WHERE id=?", (user_id,))

    async def set_banned(self, user_id: int, banned: bool, reason: str | None = None) -> bool:
        """Забанить или разбанить. Пользователь, которого ещё нет, создаётся."""
        now = _now()
        await self.conn.execute(
            "INSERT OR IGNORE INTO users (id, created_at, last_seen) VALUES (?, ?, ?)",
            (user_id, now, now),
        )
        changed = await self._write(
            "UPDATE users SET banned=?, ban_reason=? WHERE id=? AND banned<>?",
            (int(banned), reason if banned else None, user_id, int(banned)),
        )
        return changed == 1

    async def set_blocked_bot(self, user_id: int, blocked: bool = True) -> None:
        await self._write("UPDATE users SET blocked_bot=? WHERE id=?", (int(blocked), user_id))

    async def banned_users(self, limit: int = 50) -> list[User]:
        cur = await self.conn.execute(
            "SELECT id FROM users WHERE banned=1 ORDER BY last_seen DESC LIMIT ?", (limit,)
        )
        return [u for r in await cur.fetchall() if (u := await self.get_user(r["id"]))]

    async def audience(self, active_days: int | None) -> list[int]:
        """ID получателей рассылки: не забанены и не остановили бота."""
        sql = "SELECT id FROM users WHERE banned=0 AND blocked_bot=0 AND captcha_passed=1"
        params: tuple = ()
        if active_days:
            sql += " AND last_seen>=?"
            params = (_now() - active_days * 86400,)
        cur = await self.conn.execute(sql + " ORDER BY id", params)
        return [r["id"] for r in await cur.fetchall()]

    async def stats(self) -> dict[str, int]:
        now = _now()
        q = {
            "total": "SELECT count(*) FROM users",
            "passed": "SELECT count(*) FROM users WHERE captcha_passed=1",
            "banned": "SELECT count(*) FROM users WHERE banned=1",
            "blocked": "SELECT count(*) FROM users WHERE blocked_bot=1",
            "day": f"SELECT count(*) FROM users WHERE last_seen>={now - 86400}",
            "week": f"SELECT count(*) FROM users WHERE last_seen>={now - 7 * 86400}",
            "messages": "SELECT count(*) FROM group_map",
        }
        result = {}
        for key, sql in q.items():
            cur = await self.conn.execute(sql)
            result[key] = (await cur.fetchone())[0]
        return result

    # ---- связь сообщений ---------------------------------------------

    async def map_group_message(
        self, group_id: int, group_msg_id: int, user_id: int, user_msg_id: int | None
    ) -> None:
        await self._write(
            "INSERT OR REPLACE INTO group_map VALUES (?, ?, ?, ?)",
            (group_id, group_msg_id, user_id, user_msg_id),
        )

    async def by_group_message(self, group_id: int, group_msg_id: int) -> tuple[int, int | None] | None:
        cur = await self.conn.execute(
            "SELECT user_id, user_msg_id FROM group_map WHERE group_id=? AND group_msg_id=?",
            (group_id, group_msg_id),
        )
        row = await cur.fetchone()
        return (row["user_id"], row["user_msg_id"]) if row else None

    async def map_user_message(
        self, user_id: int, user_msg_id: int, group_id: int, group_msg_id: int
    ) -> None:
        await self._write(
            "INSERT OR REPLACE INTO user_map VALUES (?, ?, ?, ?)",
            (user_id, user_msg_id, group_id, group_msg_id),
        )

    async def by_user_message(self, user_id: int, user_msg_id: int) -> tuple[int, int] | None:
        cur = await self.conn.execute(
            "SELECT group_id, group_msg_id FROM user_map WHERE user_id=? AND user_msg_id=?",
            (user_id, user_msg_id),
        )
        row = await cur.fetchone()
        return (row["group_id"], row["group_msg_id"]) if row else None

    # ---- админы ---------------------------------------------------------

    async def add_admin(self, user_id: int, added_by: int) -> bool:
        return await self._write(
            "INSERT OR IGNORE INTO admins VALUES (?, ?, ?)", (user_id, added_by, _now())
        ) == 1

    async def remove_admin(self, user_id: int) -> bool:
        return await self._write("DELETE FROM admins WHERE id=?", (user_id,)) == 1

    async def admin_ids(self) -> set[int]:
        cur = await self.conn.execute("SELECT id FROM admins")
        return {r["id"] for r in await cur.fetchall()}

    # ---- настройки ------------------------------------------------------

    async def load_settings(self) -> dict[str, Any]:
        cur = await self.conn.execute("SELECT key, value FROM settings")
        return {r["key"]: json.loads(r["value"]) for r in await cur.fetchall()}

    async def save_setting(self, key: str, value: Any) -> None:
        await self._write(
            "INSERT OR REPLACE INTO settings VALUES (?, ?)",
            (key, json.dumps(value, ensure_ascii=False)),
        )
