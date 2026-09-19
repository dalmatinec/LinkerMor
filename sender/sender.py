"""Отправка сообщений с учётом лимитов и ошибок Telegram.

Единственный способ отправить сообщение в проекте. Собирает вместе три
вещи, которые иначе пришлось бы повторять в каждом модуле: ограничение
частоты, повтор после требования подождать и разбор ожидаемых отказов.

Принимает ``EntityText``, поэтому форматирование и премиум-эмодзи
сохраняются автоматически, а ``parse_mode`` не используется вовсе — текст
пользователя не может превратиться в разметку.
"""

from __future__ import annotations

import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup, Message

from core.logging import get_logger
from sender.throttle import RateLimiter
from texts.entities import EntityText

log = get_logger(__name__)

#: Сколько раз повторять отправку после требования подождать.
MAX_RETRIES = 3


class Sender:
    """Отправляет сообщения, соблюдая ограничения Telegram."""

    def __init__(self, bot: Bot, limiter: RateLimiter | None = None) -> None:
        self._bot = bot
        self._limiter = limiter or RateLimiter()

    async def send(
        self,
        chat_id: int,
        content: EntityText,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
        reply_to_message_id: int | None = None,
        message_thread_id: int | None = None,
        disable_notification: bool = False,
    ) -> Message | None:
        """Отправить текст в чат.

        Returns:
            Отправленное сообщение либо ``None``, если чат недоступен.
            Недоступность чата — ожидаемая ситуация: бота могли исключить
            между проверкой и отправкой, и наказание от этого не отменяется.
        """
        if not content.text:
            return None

        text, entities = content.to_telegram()

        for attempt in range(1, MAX_RETRIES + 1):
            await self._limiter.acquire(chat_id)
            try:
                return await self._bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    entities=entities,
                    reply_markup=reply_markup,
                    reply_to_message_id=reply_to_message_id,
                    message_thread_id=message_thread_id,
                    disable_notification=disable_notification,
                )
            except TelegramRetryAfter as exc:
                log.warning(
                    "Telegram требует паузу",
                    extra={"chat_id": chat_id, "retry_after": exc.retry_after,
                           "attempt": attempt},
                )
                if attempt == MAX_RETRIES:
                    return None
                await asyncio.sleep(exc.retry_after)
            except TelegramForbiddenError:
                log.info("чат недоступен для отправки", extra={"chat_id": chat_id})
                self._limiter.forget(chat_id)
                return None

        return None

    async def reply(
        self,
        message: Message,
        content: EntityText,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> Message | None:
        """Ответить на сообщение, сохранив ветку обсуждения."""
        return await self.send(
            message.chat.id,
            content,
            reply_markup=reply_markup,
            reply_to_message_id=message.message_id,
            message_thread_id=message.message_thread_id,
        )

    async def send_media(
        self,
        chat_id: int,
        kind: str,
        file_id: str,
        caption: EntityText | None = None,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
        reply_to_message_id: int | None = None,
        message_thread_id: int | None = None,
    ) -> Message | None:
        """Отправить вложение с подписью.

        Файл отправляется по идентификатору, полученному от Telegram при
        сохранении: повторная загрузка не нужна.
        """
        method = getattr(self._bot, f"send_{kind}", None)
        if method is None:
            log.warning("неизвестный тип вложения", extra={"kind": kind})
            return None

        text, entities = caption.to_telegram() if caption else ("", [])
        payload: dict = {
            "chat_id": chat_id,
            kind: file_id,
            "reply_markup": reply_markup,
            "reply_to_message_id": reply_to_message_id,
            "message_thread_id": message_thread_id,
        }
        # У стикеров и кружков подписи не бывает.
        if text and kind not in {"sticker", "video_note"}:
            payload["caption"] = text
            payload["caption_entities"] = entities

        await self._limiter.acquire(chat_id)
        try:
            return await method(**payload)
        except TelegramRetryAfter as exc:
            log.warning("Telegram требует паузу", extra={"chat_id": chat_id,
                                                         "retry_after": exc.retry_after})
            return None
        except TelegramForbiddenError:
            log.info("чат недоступен для отправки", extra={"chat_id": chat_id})
            self._limiter.forget(chat_id)
            return None
