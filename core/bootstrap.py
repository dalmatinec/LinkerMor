"""Сборка и разборка приложения.

Все долгоживущие объекты создаются здесь ровно один раз и передаются
хендлерам через контекст aiogram. Ни один модуль не создаёт собственное
подключение к базе или Redis.
"""

from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from cache.memory import MemoryCache
from core.config import Settings
from core.logging import get_logger
from core.registry import ModuleRegistry, build_registry
from settings.defs import SettingsRegistry, build_registry as build_settings_registry
from texts.defs import TextRegistry, build_registry as build_texts_registry
from database.engine import create_engine, create_session_factory
from middlewares.chat_context import ChatContextMiddleware
from middlewares.db_session import DbSessionMiddleware
from middlewares.error import ErrorMiddleware
from middlewares.logging import LoggingMiddleware
from middlewares.services import ServicesMiddleware
from sender.sender import Sender
from tasks.expirations import EXPIRATION_INTERVAL, make_expiration_task
from tasks.scheduler import Scheduler

log = get_logger(__name__)

#: Типы апдейтов, которые бот запрашивает у Telegram.
#: ``chat_member`` не входит в набор по умолчанию: без явного указания
#: бот не узнает о входе и выходе участников и о смене их прав.
ALLOWED_UPDATES: list[str] = [
    "message",
    "edited_message",
    "callback_query",
    "my_chat_member",
    "chat_member",
    "chat_join_request",
]


@dataclass(slots=True)
class AppContext:
    """Живые ресурсы приложения."""

    settings: Settings
    bot: Bot
    dispatcher: Dispatcher
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    redis: Redis
    cache: MemoryCache
    scheduler: Scheduler
    registry: ModuleRegistry
    settings_registry: SettingsRegistry
    text_registry: TextRegistry

    async def shutdown(self) -> None:
        """Корректно освободить ресурсы. Порядок важен."""
        await self.scheduler.stop()
        await self.bot.session.close()
        await self.engine.dispose()
        await self.redis.aclose()
        await self.cache.clear()
        log.info("ресурсы освобождены")


def build_app(settings: Settings) -> AppContext:
    """Собрать приложение из конфигурации."""
    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=None),  # форматирование задаём entities
    )

    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    dispatcher = Dispatcher(storage=RedisStorage(redis=redis))

    sender = Sender(bot)

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    cache = MemoryCache()

    specs = ENABLED_MODULES()
    registry = build_registry(specs)
    settings_registry = build_settings_registry(specs)
    text_registry = build_texts_registry(specs)

    # Порядок важен: контекст логирования → перехват ошибок → сессия базы
    # → контекст чата. Упавший хендлер логируется уже с correlation id, а
    # транзакция закрывается до того, как ошибка покинет обработку.
    dispatcher.update.outer_middleware(LoggingMiddleware())
    dispatcher.update.outer_middleware(
        ErrorMiddleware(session_factory, cache, text_registry)
    )
    dispatcher.update.outer_middleware(DbSessionMiddleware(session_factory))
    dispatcher.update.outer_middleware(ChatContextMiddleware())
    dispatcher.update.outer_middleware(
        ServicesMiddleware(settings, cache, settings_registry, text_registry, sender)
    )

    registry.attach(dispatcher)

    log.info(
        "реестры собраны",
        extra={
            "modules": len(registry.specs),
            "settings": len(settings_registry),
            "texts": len(text_registry),
        },
    )

    dispatcher["settings"] = settings
    dispatcher["session_factory"] = session_factory
    dispatcher["cache"] = cache
    dispatcher["redis"] = redis
    scheduler = Scheduler()
    scheduler.add(
        "expirations", EXPIRATION_INTERVAL, make_expiration_task(session_factory)
    )

    dispatcher["sender"] = sender
    dispatcher["registry"] = registry
    dispatcher["settings_registry"] = settings_registry
    dispatcher["text_registry"] = text_registry

    return AppContext(
        settings=settings,
        bot=bot,
        dispatcher=dispatcher,
        engine=engine,
        session_factory=session_factory,
        redis=redis,
        cache=cache,
        scheduler=scheduler,
        registry=registry,
        settings_registry=settings_registry,
        text_registry=text_registry,
    )


def ENABLED_MODULES() -> list:  # noqa: N802 - список включённых модулей проекта
    """Единственное место, где перечислены модули приложения.

    Подключение нового модуля — импорт его ``spec`` и одна строка здесь.
    Порядок в списке значения не имеет: очередь определяет ``priority``.
    """
    from mod_admin.spec import MODULE as admin
    from mod_chats.spec import MODULE as chats
    from mod_moderation.spec import MODULE as moderation
    from mod_triggers.spec import MODULE as triggers

    return [chats, admin, moderation, triggers]
