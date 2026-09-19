"""Движок SQLAlchemy и фабрика сессий.

Пул соединений создаётся один раз на процесс: новое подключение к базе
на каждый апдейт — прямое нарушение ТЗ §24 и заметная потеря времени.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from core.config import Settings
from core.logging import get_logger

log = get_logger(__name__)


def create_engine(settings: Settings) -> AsyncEngine:
    """Создать движок с пулом соединений."""
    engine = create_async_engine(
        settings.database_url,
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,  # отсекает соединения, умершие после простоя
        pool_recycle=1800,
    )
    log.info(
        "движок базы создан",
        extra={"pool_size": settings.db_pool_size, "max_overflow": settings.db_max_overflow},
    )
    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Фабрика сессий. Одна сессия живёт ровно один апдейт."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,  # объекты остаются читаемыми после commit
        autoflush=False,
    )
