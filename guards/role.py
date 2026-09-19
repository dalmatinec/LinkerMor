"""Фильтры по роли пользователя в конкретном чате.

Роль всегда вычисляется для того чата, где пришёл апдейт: глобального
«администратора бота» в проекте нет, кроме владельца из ``OWNER_IDS``.
"""

from __future__ import annotations

from typing import Any

from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message, TelegramObject

from core.constants import Role
from permissions.service import PermissionService


def _actor(event: TelegramObject) -> tuple[int | None, int | None]:
    """Кто и где: идентификаторы пользователя и чата события."""
    if isinstance(event, CallbackQuery):
        message = event.message
        chat_id = message.chat.id if message is not None else None
        return event.from_user.id if event.from_user else None, chat_id
    if isinstance(event, Message):
        return (event.from_user.id if event.from_user else None), event.chat.id
    user = getattr(event, "from_user", None)
    chat = getattr(event, "chat", None)
    return (user.id if user else None), (chat.id if chat else None)


class HasRole(Filter):
    """Пропускает, если роль в этом чате не ниже указанной."""

    def __init__(self, minimum: Role) -> None:
        self.minimum = minimum

    async def __call__(self, event: TelegramObject, **data: Any) -> bool:
        permissions: PermissionService | None = data.get("permissions")
        user_id, chat_id = _actor(event)
        if permissions is None or user_id is None or chat_id is None:
            return False

        return await permissions.has_role(
            chat_id,
            user_id,
            self.minimum,
            member=data.get("member"),
            is_anonymous=bool(data.get("is_anonymous_admin")),
        )


class IsOwner(Filter):
    """Только владелец бота. Единственная глобальная проверка (ТЗ §4)."""

    async def __call__(self, event: TelegramObject, **data: Any) -> bool:
        config = data.get("config")
        user = getattr(event, "from_user", None)
        return config is not None and user is not None and config.is_owner(user.id)
