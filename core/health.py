"""Проверка состояния бота.

Два независимых слоя, потому что один не закрывает задачу целиком:

* **Самодиагностика.** Бот сам проверяет базу, Redis и связь с Telegram и
  сообщает владельцу, когда что-то отвалилось. Работает, пока жив сам бот.
* **Внешний сторож.** Бот регулярно дёргает внешний адрес. Если сигналы
  прекратились, тревогу поднимает внешняя служба — именно тогда, когда
  бот молчит и сказать о себе ничего не может.

Без второго слоя падение процесса осталось бы незамеченным: мёртвый
процесс не отправляет сообщений.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import aiohttp
from aiogram import Bot
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from core.logging import get_logger

log = get_logger(__name__)

#: Таймаут одной проверки. Дольше ждать нет смысла: значит, уже плохо.
CHECK_TIMEOUT = 5.0


@dataclass(slots=True)
class ComponentState:
    """Состояние одной подсистемы."""

    name: str
    ok: bool
    detail: str = ""
    latency_ms: float = 0.0


@dataclass(slots=True)
class HealthReport:
    """Итог проверки."""

    components: list[ComponentState] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(component.ok for component in self.components)

    @property
    def failed(self) -> list[ComponentState]:
        return [component for component in self.components if not component.ok]

    def describe(self) -> str:
        lines = []
        for component in self.components:
            mark = "в порядке" if component.ok else f"сбой — {component.detail}"
            lines.append(f"{component.name}: {mark} ({component.latency_ms:.0f} мс)")
        return "\n".join(lines)


class HealthService:
    """Проверяет доступность всего, без чего бот не работает."""

    def __init__(self, engine: AsyncEngine, redis: Redis, bot: Bot) -> None:
        self._engine = engine
        self._redis = redis
        self._bot = bot

    async def check(self) -> HealthReport:
        """Проверить все подсистемы."""
        return HealthReport(
            components=[
                await self._check_database(),
                await self._check_redis(),
                await self._check_telegram(),
            ]
        )

    async def _check_database(self) -> ComponentState:
        started = time.monotonic()
        try:
            async with self._engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return ComponentState("База данных", True, latency_ms=_elapsed(started))
        except Exception as exc:
            return ComponentState("База данных", False, str(exc)[:200], _elapsed(started))

    async def _check_redis(self) -> ComponentState:
        started = time.monotonic()
        try:
            await self._redis.ping()
            return ComponentState("Redis", True, latency_ms=_elapsed(started))
        except Exception as exc:
            return ComponentState("Redis", False, str(exc)[:200], _elapsed(started))

    async def _check_telegram(self) -> ComponentState:
        started = time.monotonic()
        try:
            me = await self._bot.get_me()
            return ComponentState(
                "Telegram", True, f"@{me.username}", _elapsed(started)
            )
        except Exception as exc:
            return ComponentState("Telegram", False, str(exc)[:200], _elapsed(started))


async def ping_watchdog(url: str) -> bool:
    """Подать сигнал внешнему сторожу.

    Сторож ждёт сигналы по расписанию и поднимает тревогу, когда они
    прекращаются. Подойдёт любая служба такого рода — healthchecks.io,
    Better Uptime, собственный скрипт.
    """
    if not url:
        return False

    try:
        timeout = aiohttp.ClientTimeout(total=CHECK_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as http:
            async with http.get(url) as response:
                return response.status < 400
    except Exception as exc:
        log.warning("не удалось подать сигнал сторожу", extra={"reason": str(exc)})
        return False


def _elapsed(started: float) -> float:
    return (time.monotonic() - started) * 1000
