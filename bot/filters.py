"""Фильтры хендлеров. Настройки приходят из данных диспетчера."""

from __future__ import annotations

from aiogram.types import CallbackQuery, Message

from bot.settings import Settings


async def in_work_group(event: Message | CallbackQuery, settings: Settings) -> bool:
    chat = event.chat if isinstance(event, Message) else (event.message and event.message.chat)
    return chat is not None and settings.group_id is not None and chat.id == settings.group_id


async def is_admin(event: Message | CallbackQuery, settings: Settings) -> bool:
    return event.from_user is not None and settings.is_admin(event.from_user.id)


async def is_owner(event: Message | CallbackQuery, settings: Settings) -> bool:
    return event.from_user is not None and settings.is_owner(event.from_user.id)
