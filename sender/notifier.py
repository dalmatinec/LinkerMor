"""Уведомления владельцу бота.

Владелец должен узнавать о поломках, но не ценой потока одинаковых
сообщений: одна ошибка в популярном чате способна повториться тысячу раз
за минуту. Поэтому уведомления подавляются по подписи — повторное
сообщение о том же самом не отправляется, пока не истечёт пауза.
"""

from __future__ import annotations

import hashlib
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from cache.backend import CacheBackend
from cache.keys import GlobalEntity, global_key
from core.logging import get_logger
from texts.entities import EntityText

log = get_logger(__name__)

#: Пауза между одинаковыми уведомлениями.
DEFAULT_MUTE_SECONDS = 1800

#: Предел уведомлений в час независимо от их содержания. Защищает от
#: ситуации, когда ломается сразу всё и каждая поломка своя.
HOURLY_LIMIT = 20


class OwnerNotifier:
    """Отправляет владельцам сообщения о состоянии бота."""

    def __init__(self, bot: Bot, owner_ids: frozenset[int], cache: CacheBackend) -> None:
        self._bot = bot
        self._owner_ids = owner_ids
        self._cache = cache

    async def notify(
        self,
        text: str,
        *,
        signature: str | None = None,
        mute_seconds: int = DEFAULT_MUTE_SECONDS,
        force: bool = False,
    ) -> bool:
        """Сообщить владельцам.

        Args:
            text: Готовый текст сообщения.
            signature: Подпись события. Одинаковые подписи подавляются.
            mute_seconds: Насколько замолчать по этой подписи.
            force: Отправить в обход ограничений — для запуска и остановки.

        Returns:
            ``True``, если сообщение действительно отправлено.
        """
        if not self._owner_ids:
            return False

        if not force:
            if signature is not None and not await self._claim(signature, mute_seconds):
                return False
            if not await self._within_hourly_limit():
                return False

        delivered = False
        content = EntityText(text=text[:4000])
        body, entities = content.to_telegram()

        for owner_id in self._owner_ids:
            try:
                await self._bot.send_message(
                    chat_id=owner_id, text=body, entities=entities,
                    disable_notification=not force,
                )
                delivered = True
            except TelegramAPIError as exc:
                # Владелец мог не начать диалог с ботом — это не поломка.
                log.debug(
                    "не удалось уведомить владельца",
                    extra={"target_id": owner_id, "reason": str(exc)},
                )

        return delivered

    async def notify_error(self, error: BaseException, context: dict[str, Any]) -> bool:
        """Сообщить о необработанной ошибке.

        Подпись собирается из типа ошибки и места возникновения, поэтому
        повторы одной и той же поломки не превращаются в поток сообщений.
        """
        where = context.get("handler") or context.get("module") or "неизвестно"
        signature = hashlib.sha1(
            f"{type(error).__name__}:{where}".encode()
        ).hexdigest()[:12]

        details = "\n".join(f"{key}: {value}" for key, value in context.items() if value)
        text = (
            f"Ошибка в боте\n\n"
            f"{type(error).__name__}: {error}\n\n"
            f"{details}"
        )
        return await self.notify(text, signature=signature)

    async def _claim(self, signature: str, mute_seconds: int) -> bool:
        """Занять подпись. Возвращает ``False``, если о ней уже сообщали."""
        key = global_key(GlobalEntity.SYSTEM_SETTINGS, "notify", signature)
        if await self._cache.get(key) is not None:
            return False
        await self._cache.set(key, True, ttl=mute_seconds)
        return True

    async def _within_hourly_limit(self) -> bool:
        key = global_key(GlobalEntity.SYSTEM_SETTINGS, "notify_count")
        return await self._cache.incr(key, ttl=3600) <= HOURLY_LIMIT
