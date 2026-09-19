"""Перехват ошибок: пользователь никогда не видит traceback (ТЗ §28)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.types import CallbackQuery, Message, TelegramObject

from core.errors import LinkerMorError
from core.logging import get_logger

log = get_logger(__name__)

#: Временная заглушка на время Phase 1. С появлением TextService (Phase 3)
#: эти строки заменяются обращением к системе Custom Texts по ``text_key``.
_FALLBACK_TEXT = "Не удалось выполнить действие. Попробуйте позже."


class ErrorMiddleware(BaseMiddleware):
    """Ловит исключения хендлеров и отвечает человеку понятным текстом."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except LinkerMorError as exc:
            # Ожидаемая ошибка предметной области: логируем без traceback.
            log.warning(
                "действие отклонено",
                extra={"text_key": exc.text_key, "reason": str(exc), **exc.context},
            )
            await _reply(event, _FALLBACK_TEXT)
        except TelegramRetryAfter as exc:
            log.warning("превышен лимит Telegram", extra={"retry_after": exc.retry_after})
        except TelegramAPIError as exc:
            log.error("ошибка Telegram API", extra={"method": type(exc).__name__}, exc_info=True)
            await _reply(event, _FALLBACK_TEXT)
        except Exception:
            log.exception("необработанное исключение")
            await _reply(event, _FALLBACK_TEXT)
        return None


async def _reply(event: TelegramObject, text: str) -> None:
    """Сообщить пользователю об ошибке, не поднимая новую ошибку."""
    inner = event.event if hasattr(event, "event") else event
    try:
        if isinstance(inner, CallbackQuery):
            await inner.answer(text, show_alert=True)
        elif isinstance(inner, Message):
            await inner.reply(text)
    except TelegramAPIError:
        log.debug("не удалось доставить сообщение об ошибке")
