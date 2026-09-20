"""Фильтр наличия у бота права Telegram.

Отличается от проверки внутри хендлера тем, что при отсутствии права
хендлер не запускается вовсе. Применяется там, где без права действие
бессмысленно целиком — например, пункт меню модерации не должен
показываться, если бот не умеет ограничивать участников.
"""

from __future__ import annotations

from typing import Any

from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message, TelegramObject

from core.constants import BotPermission
from permissions.service import PermissionService


class BotCan(Filter):
    """Пропускает, если у бота есть указанное право в этом чате."""

    def __init__(self, permission: BotPermission | str) -> None:
        self.permission = permission

    async def __call__(self, event: TelegramObject, **data: Any) -> bool:
        permissions: PermissionService | None = data.get("permissions")
        if permissions is None:
            return False

        if isinstance(event, CallbackQuery):
            message = event.message
            chat_id = message.chat.id if message is not None else None
        elif isinstance(event, Message):
            chat_id = event.chat.id
        else:
            chat = getattr(event, "chat", None)
            chat_id = chat.id if chat is not None else None

        if chat_id is None:
            return False
        return await permissions.bot_can(chat_id, self.permission)
