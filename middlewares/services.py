"""Сборка сервисов для каждого апдейта.

Сервисы живут ровно один апдейт, потому что привязаны к его сессии базы.
Собираются в одном месте, чтобы хендлеры получали готовые объекты и не
конструировали их сами — иначе один хендлер неизбежно соберёт сервис
иначе, чем другой.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from cache.backend import CacheBackend
from core.config import Settings
from permissions.service import PermissionService
from resolver.user_resolver import UserResolver
from sender.sender import Sender
from settings.defs import SettingsRegistry
from settings.service import SettingsService
from texts.defs import TextRegistry
from texts.service import TextService


class ServicesMiddleware(BaseMiddleware):
    """Кладёт в контекст хендлера готовые сервисы."""

    def __init__(
        self,
        config: Settings,
        cache: CacheBackend,
        settings_registry: SettingsRegistry,
        text_registry: TextRegistry,
        sender: Sender,
    ) -> None:
        self._config = config
        self._cache = cache
        self._settings_registry = settings_registry
        self._text_registry = text_registry
        self._sender = sender

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session = data.get("session")
        if session is None:
            return await handler(event, data)

        bot = data.get("bot")
        data["settings"] = SettingsService(session, self._cache, self._settings_registry)
        data["texts"] = TextService(
            session, self._cache, self._text_registry, self._config.default_language
        )
        data["permissions"] = PermissionService(
            session,
            self._cache,
            self._config.owner_ids,
            bot_id=bot.id if bot is not None else None,
        )
        data["resolver"] = UserResolver(session)
        data["sender"] = self._sender
        data["config"] = self._config

        return await handler(event, data)
