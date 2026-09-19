"""Перехват ошибок: пользователь никогда не видит traceback (ТЗ §28).

Сообщение об ошибке берётся из системы Custom Texts по ключу, объявленному
самой ошибкой, поэтому администратор чата может переформулировать любое из
них под свой чат.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cache.backend import CacheBackend
from core.errors import LinkerMorError
from core.logging import get_logger
from sender.notifier import OwnerNotifier
from texts.defs import TextRegistry
from texts.service import TextService

log = get_logger(__name__)


class ErrorMiddleware(BaseMiddleware):
    """Ловит исключения хендлеров и отвечает человеку понятным текстом."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        cache: CacheBackend,
        text_registry: TextRegistry,
        notifier: OwnerNotifier | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._cache = cache
        self._registry = text_registry
        self._notifier = notifier

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except LinkerMorError as exc:
            # Ожидаемая ошибка предметной области: traceback не нужен.
            log.warning(
                "действие отклонено",
                extra={"text_key": exc.text_key, "reason": str(exc), **exc.context},
            )
            await self._reply(event, exc.text_key, exc.context)
        except TelegramRetryAfter as exc:
            # Отвечать нечем: лимит распространяется и на сообщение об ошибке.
            log.warning("превышен лимит Telegram", extra={"retry_after": exc.retry_after})
        except TelegramAPIError:
            log.error("ошибка Telegram API", exc_info=True)
            await self._reply(event, "error_unknown", {})
        except Exception as exc:
            log.exception("необработанное исключение")
            await self._reply(event, "error_unknown", {})
            # Владелец должен узнать о поломке, не читая логи на сервере.
            if self._notifier is not None:
                await self._notifier.notify_error(
                    exc,
                    {
                        "handler": getattr(handler, "__qualname__", ""),
                        "chat_id": data.get("event_chat").id
                        if data.get("event_chat") is not None
                        else None,
                        "user_id": data.get("event_from_user").id
                        if data.get("event_from_user") is not None
                        else None,
                        "correlation_id": data.get("correlation_id"),
                    },
                )
        return None

    async def _reply(self, event: TelegramObject, text_key: str, values: dict[str, Any]) -> None:
        """Сообщить пользователю об ошибке, не поднимая новую ошибку.

        Транзакция обработки уже откачена, поэтому текст читается в
        отдельной короткоживущей сессии.
        """
        inner = event.event if hasattr(event, "event") else event
        target = inner if isinstance(inner, (Message, CallbackQuery)) else None
        if target is None:
            return

        try:
            chat = getattr(target, "chat", None) or getattr(
                getattr(target, "message", None), "chat", None
            )
            async with self._session_factory() as session:
                service = TextService(session, self._cache, self._registry)
                rendered = await service.render(
                    chat.id if chat is not None else None,
                    text_key,
                    {k: str(v) for k, v in values.items()},
                )
            text, entities = rendered.to_telegram()

            if isinstance(target, CallbackQuery):
                await target.answer(text[:200], show_alert=True)
            else:
                await target.reply(text, entities=entities)
        except TelegramAPIError:
            log.debug("не удалось доставить сообщение об ошибке")
        except Exception:
            # Ошибка при выводе ошибки не должна ронять обработку апдейта.
            log.exception("сбой при формировании сообщения об ошибке")
