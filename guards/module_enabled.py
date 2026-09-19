"""Фильтр включённости модуля в конкретном чате.

Выключенный модуль не должен отвечать вовсе: его хендлеры для этого чата
как будто не существуют.
"""

from __future__ import annotations

from typing import Any

from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message, TelegramObject

from settings.service import SettingsService


class ModuleEnabled(Filter):
    """Пропускает, только если модуль включён в этом чате."""

    def __init__(self, module: str) -> None:
        self.module = module

    async def __call__(self, event: TelegramObject, **data: Any) -> bool:
        settings: SettingsService | None = data.get("settings")
        if settings is None:
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
        return await settings.is_module_enabled(chat_id, self.module)
