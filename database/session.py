"""Управление жизненным циклом сессии базы данных."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@asynccontextmanager
async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Сессия с автоматическим commit при успехе и rollback при ошибке.

    Используется фоновыми задачами и тестами. В обработке апдейтов сессию
    выдаёт middleware, чтобы все хендлеры одного апдейта работали в общей
    транзакции.
    """
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()
