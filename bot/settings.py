"""Настройки бота, которые меняются из админки.

Значения лежат в таблице ``settings`` и держатся в памяти процесса: бот
работает одним экземпляром, поэтому чтение настроек не ходит в базу.
"""

from __future__ import annotations

from typing import Any

from bot.db import Database

DEFAULTS: dict[str, Any] = {
    "group_id": None,           # рабочая группа
    "group_title": None,
    "captcha": True,            # капча при /start
    "text_only": True,          # пользователи пишут только текстом
    "flood_limit": 3,           # не больше стольких сообщений
    "flood_window": 10,         # за столько секунд
    "flood_mute": 30,           # пауза после превышения, секунд
    "welcome": None,            # своё приветствие (сохранённое сообщение)
    "start_ad": None,           # реклама после приветствия
    "start_ad_on": False,
    "last_broadcast": 0,        # время последней рассылки
}

# Границы, в которых админка разрешает двигать числа.
LIMITS: dict[str, tuple[int, int]] = {
    "flood_limit": (1, 30),
    "flood_window": (2, 300),
    "flood_mute": (5, 3600),
}


class Settings:
    def __init__(self, db: Database, owner_ids: frozenset[int]) -> None:
        self._db = db
        self._values: dict[str, Any] = dict(DEFAULTS)
        self.owner_ids = owner_ids
        self._admins: set[int] = set()

    async def load(self) -> None:
        self._values.update(await self._db.load_settings())
        self._admins = await self._db.admin_ids()

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    async def set(self, key: str, value: Any) -> None:
        if key not in DEFAULTS:
            raise KeyError(key)
        if key in LIMITS:
            lo, hi = LIMITS[key]
            value = max(lo, min(hi, int(value)))
        self._values[key] = value
        await self._db.save_setting(key, value)

    @property
    def group_id(self) -> int | None:
        return self._values["group_id"]

    # ---- права ----------------------------------------------------------

    def is_owner(self, user_id: int) -> bool:
        return user_id in self.owner_ids

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.owner_ids or user_id in self._admins

    @property
    def admins(self) -> set[int]:
        return set(self._admins)

    async def add_admin(self, user_id: int, added_by: int) -> bool:
        added = await self._db.add_admin(user_id, added_by)
        self._admins.add(user_id)
        return added

    async def remove_admin(self, user_id: int) -> bool:
        removed = await self._db.remove_admin(user_id)
        self._admins.discard(user_id)
        return removed
