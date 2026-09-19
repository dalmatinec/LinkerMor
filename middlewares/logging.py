"""Присвоение correlation id каждому апдейту (ТЗ §28)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from core.logging import (
    chat_id as chat_id_var,
)
from core.logging import (
    correlation_id as correlation_id_var,
)
from core.logging import (
    get_logger,
    new_correlation_id,
)
from core.logging import (
    update_id as update_id_var,
)
from core.logging import (
    user_id as user_id_var,
)

log = get_logger(__name__)


class LoggingMiddleware(BaseMiddleware):
    """Наполняет контекст логирования данными апдейта.

    Ставится внешним слоем, поэтому все последующие middleware, хендлеры и
    сервисы пишут логи уже с correlation id, chat_id и user_id.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        correlation = new_correlation_id()
        tokens = [
            correlation_id_var.set(correlation),
            update_id_var.set(event.update_id if isinstance(event, Update) else None),
            chat_id_var.set(_extract_chat_id(event)),
            user_id_var.set(_extract_user_id(data)),
        ]
        data["correlation_id"] = correlation
        try:
            return await handler(event, data)
        finally:
            for token in tokens:
                token.var.reset(token)


def _extract_chat_id(event: TelegramObject) -> int | None:
    if not isinstance(event, Update):
        return None
    inner = event.event
    chat = getattr(inner, "chat", None)
    if chat is not None:
        return int(chat.id)
    message = getattr(inner, "message", None)
    if message is not None and getattr(message, "chat", None) is not None:
        return int(message.chat.id)
    return None


def _extract_user_id(data: dict[str, Any]) -> int | None:
    user = data.get("event_from_user")
    return int(user.id) if user is not None else None
