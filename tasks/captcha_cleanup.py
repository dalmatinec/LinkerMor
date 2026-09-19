"""Закрытие просроченных проверок при входе.

Без этой задачи человек, не прошедший проверку, остался бы в муте
навсегда: срок проверки хранится в базе, но сам по себе ничего не делает.
"""

from __future__ import annotations

from aiogram import Bot
from sqlalchemy.ext.asyncio import async_sessionmaker

from cache.backend import CacheBackend
from core.config import Settings
from core.logging import get_logger
from database.session import session_scope
from mod_captcha.service import CaptchaService
from mod_moderation.actions import ModerationActions
from mod_moderation.service import ModerationService
from permissions.service import PermissionService
from settings.defs import SettingsRegistry
from settings.service import SettingsService

log = get_logger(__name__)

#: Раз в полминуты: точность проверки важнее экономии запросов, потому что
#: всё это время человек не может писать.
CAPTCHA_CLEANUP_INTERVAL = 30.0


def make_captcha_cleanup_task(
    session_factory: async_sessionmaker,
    bot: Bot,
    cache: CacheBackend,
    config: Settings,
    settings_registry: SettingsRegistry,
):
    """Собрать задачу закрытия просроченных проверок."""

    async def run() -> None:
        async with session_scope(session_factory) as session:
            settings = SettingsService(session, cache, settings_registry)
            permissions = PermissionService(session, cache, config.owner_ids, bot_id=bot.id)
            moderation = ModerationService(session, bot, permissions, settings)
            service = CaptchaService(session, settings, permissions, moderation)

            expired = await service.collect_expired()
            for row in expired:
                await service.punish(row.chat_id, row.user_id)
                if row.message_id:
                    await ModerationActions(bot).delete_message(row.chat_id, row.message_id)
                await session.delete(row)

            if expired:
                log.info("закрыты просроченные проверки", extra={"count": len(expired)})

    return run
