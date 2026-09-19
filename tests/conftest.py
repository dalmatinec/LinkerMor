"""Общие фикстуры тестов."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cache.memory import MemoryCache  # noqa: E402
from core.config import Settings  # noqa: E402

#: Токен формата Telegram, не принадлежащий реальному боту.
FAKE_TOKEN = "123456789:TESTTESTTESTTESTTESTTESTTESTTESTTES"


@pytest.fixture
def settings() -> Settings:
    """Валидная конфигурация без чтения .env."""
    return Settings(
        _env_file=None,
        bot_token=FAKE_TOKEN,
        owner_ids_raw="111,222",
        postgres_password="secret",
    )


@pytest.fixture
def cache() -> MemoryCache:
    return MemoryCache()


@pytest.fixture
def project_root() -> Path:
    return PROJECT_ROOT


# ─── База данных ─────────────────────────────────────────────────────────────

import os  # noqa: E402
from collections.abc import AsyncIterator  # noqa: E402

import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import mod_chats.models  # noqa: E402,F401 — наполняет Base.metadata
from database.base import Base  # noqa: E402

#: Тесты работают на настоящем PostgreSQL: проект опирается на JSONB,
#: частичные индексы и ON CONFLICT, которых нет в SQLite.
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://linkermor:linkermor@127.0.0.1:5432/linkermor_test",
)


@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncIterator:
    """Движок тестовой базы со свежей схемой.

    NullPool обязателен: pytest-asyncio выполняет тесты в разных event loop,
    а соединение asyncpg привязано к тому циклу, в котором создано.
    Без него переиспользованное соединение падает с «another operation is
    in progress».
    """
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_tables(engine) -> AsyncIterator[None]:
    """Очистка таблиц после каждого теста.

    Автоматическая, потому что часть тестов фиксирует транзакцию (проверка
    сохранности данных после перезапуска). Без неё такие тесты оставляли бы
    записи следующим, и результат зависел бы от порядка запуска.
    """
    yield
    factory = async_sessionmaker(bind=engine, class_=AsyncSession)
    async with factory() as cleanup:
        for table in reversed(Base.metadata.sorted_tables):
            await cleanup.execute(table.delete())
        await cleanup.commit()


@pytest_asyncio.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    """Сессия теста. Незафиксированные изменения откатываются."""
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    """Фабрика сессий для тестов, которым нужно несколько подключений."""
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
