"""Учёт активности участников.

Сделано middleware, а не хендлером, по существенной причине: в aiogram
первый подошедший хендлер останавливает цепочку. Сборщик, подписанный на
все сообщения, перехватывал бы их и не давал работать антиспаму,
триггерам, репутации и рангам.

Пассивный сбор данных вообще не должен претендовать на обработку
события — его место до маршрутизации.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, Update

from core.logging import get_logger

log = get_logger(__name__)

GROUP_TYPES = frozenset({"group", "supergroup"})


class ActivityMiddleware(BaseMiddleware):
    """Считает сообщения участников для рангов и статистики."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        await self._count(event, data)
        return await handler(event, data)

    @staticmethod
    async def _count(event: TelegramObject, data: dict[str, Any]) -> None:
        session = data.get("session")
        if session is None or not isinstance(event, Update):
            return

        message = event.message
        if message is None or not isinstance(message, Message):
            return
        if message.chat.type not in GROUP_TYPES:
            return
        if not (message.text or message.caption):
            return

        user = message.from_user
        if user is None or user.is_bot:
            return

        from mod_chats.repo import MemberRepository
        from mod_stats.repo import StatsRepository

        members = MemberRepository(session)
        await members.ensure_exists(message.chat.id, user.id)
        total = await members.increment_messages(message.chat.id, user.id)
        await StatsRepository(session).register_message(message.chat.id, user.id)

        # Свежее значение счётчика пригодится рангам без повторного запроса.
        data["messages_total"] = total
