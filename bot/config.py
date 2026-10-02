"""Конфигурация из переменных окружения или файла ``.env``."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    """Подхватить ``.env``, не перезаписывая уже заданные переменные."""
    file = Path(path)
    if not file.is_file():
        return
    for raw in file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def _int_set(raw: str) -> frozenset[int]:
    return frozenset(int(x) for x in raw.replace(";", ",").split(",") if x.strip())


@dataclass(frozen=True)
class Config:
    bot_token: str
    owner_ids: frozenset[int]
    db_path: str = "data/bot.db"
    # Лимиты исходящих сообщений (ограничения Telegram).
    global_rate: float = 25.0          # сообщений в секунду на весь бот
    private_burst: int = 3             # в личку: столько сообщений
    private_period: float = 2.0        # за столько секунд
    group_per_minute: int = 20         # в рабочую группу в минуту
    broadcast_rate: float = 15.0       # рассылка, сообщений в секунду
    request_timeout: int = 60          # таймаут запроса к Telegram, секунд
    proxy: str | None = None           # socks5:// или http://, если Telegram недоступен напрямую
    ipv4_only: bool = True             # не ходить к Telegram по IPv6

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()
        token = os.environ.get("BOT_TOKEN", "").strip()
        if not token:
            raise SystemExit("BOT_TOKEN не задан: укажите его в .env")
        owners = _int_set(os.environ.get("OWNER_IDS", ""))
        if not owners:
            raise SystemExit("OWNER_IDS не задан: укажите свой Telegram ID в .env")
        env = os.environ.get
        return cls(
            bot_token=token,
            owner_ids=owners,
            db_path=env("DB_PATH", cls.db_path),
            global_rate=float(env("GLOBAL_RATE", cls.global_rate)),
            private_burst=int(env("PRIVATE_BURST", cls.private_burst)),
            private_period=float(env("PRIVATE_PERIOD", cls.private_period)),
            group_per_minute=int(env("GROUP_PER_MINUTE", cls.group_per_minute)),
            broadcast_rate=float(env("BROADCAST_RATE", cls.broadcast_rate)),
            request_timeout=int(env("REQUEST_TIMEOUT", cls.request_timeout)),
            proxy=env("PROXY") or None,
            ipv4_only=env("IPV4_ONLY", "1").strip().lower() not in {"0", "false", "no"},
        )
