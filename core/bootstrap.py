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
from database.engine import create_engine, create_session_factory
from middlewares.error import ErrorMiddleware
from middlewares.logging import LoggingMiddleware

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
    registry: ModuleRegistry

    async def shutdown(self) -> None:
        """Корректно освободить ресурсы. Порядок важен."""
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

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    cache = MemoryCache()

    # Порядок внешних middleware: сначала контекст логирования, затем
    # перехват ошибок — чтобы упавший хендлер писался уже с correlation id.
    for observer in (dispatcher.update.outer_middleware,):
        observer(LoggingMiddleware())
        observer(ErrorMiddleware())

    registry = build_registry(ENABLED_MODULES())
    registry.attach(dispatcher)

    dispatcher["settings"] = settings
    dispatcher["session_factory"] = session_factory
    dispatcher["cache"] = cache
    dispatcher["redis"] = redis
    dispatcher["registry"] = registry

    return AppContext(
        settings=settings,
        bot=bot,
        dispatcher=dispatcher,
        engine=engine,
        session_factory=session_factory,
        redis=redis,
        cache=cache,
        registry=registry,
    )


def ENABLED_MODULES() -> list:  # noqa: N802 - список включённых модулей проекта
    """Единственное место, где перечислены модули приложения.

    Подключение нового модуля — импорт его ``spec`` и одна строка здесь.
    Порядок в списке значения не имеет: очередь определяет ``priority``.
    """
    return []
