"""Фильтры по типу чата.

Каждый хендлер обязан объявлять фильтры явно: «голых» подписок на все
сообщения в проекте нет.

Тонкость, на которой легко споткнуться: у нажатия кнопки нет поля
``chat``. Чат нажатия определяется по сообщению, к которому прикреплена
клавиатура, поэтому тип чата извлекается через общую функцию, а не
обращением к полю напрямую.
"""

from __future__ import annotations

from aiogram.types import CallbackQuery, Message, TelegramObject
from aiogram.filters import Filter

GROUP_TYPES = frozenset({"group", "supergroup"})


def chat_type_of(event: TelegramObject) -> str | None:
    """Тип чата события: сообщения, нажатия кнопки или служебного события."""
    if isinstance(event, CallbackQuery):
        message = event.message
        return message.chat.type if message is not None else None

    chat = getattr(event, "chat", None)
    return chat.type if chat is not None else None


class InGroup(Filter):
    """Только группы и супергруппы."""

    async def __call__(self, event: TelegramObject) -> bool:
        return chat_type_of(event) in GROUP_TYPES


class InPrivate(Filter):
    """Только личная переписка с ботом: панели владельца и администратора."""

    async def __call__(self, event: TelegramObject) -> bool:
        return chat_type_of(event) == "private"


class IsMigration(Filter):
    """Служебное сообщение о переезде группы в супергруппу."""

    async def __call__(self, message: Message) -> bool:
        return message.migrate_to_chat_id is not None
