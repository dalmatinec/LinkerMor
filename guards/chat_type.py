"""Фильтры по типу чата.

Каждый хендлер обязан объявлять фильтры явно: «голых» подписок на все
сообщения в проекте нет.
"""

from __future__ import annotations

from aiogram.filters import Filter
from aiogram.types import Message, TelegramObject


class InGroup(Filter):
    """Только группы и супергруппы."""

    async def __call__(self, event: TelegramObject) -> bool:
        chat = getattr(event, "chat", None)
        return chat is not None and chat.type in {"group", "supergroup"}


class InPrivate(Filter):
    """Только личная переписка с ботом: панели владельца и администратора."""

    async def __call__(self, event: TelegramObject) -> bool:
        chat = getattr(event, "chat", None)
        return chat is not None and chat.type == "private"


class IsMigration(Filter):
    """Служебное сообщение о переезде группы в супергруппу."""

    async def __call__(self, message: Message) -> bool:
        return message.migrate_to_chat_id is not None
