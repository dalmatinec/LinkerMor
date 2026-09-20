"""Одна сессия базы на апдейт (ТЗ §24, критерий приёмки §32.19).

Сессия берётся из общего пула соединений, созданного при старте. Новое
подключение к базе на каждый апдейт не создаётся никогда.

Все хендлеры одного апдейта работают в общей транзакции: она фиксируется
после успешной обработки и откатывается целиком при ошибке.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class DbSessionMiddleware(BaseMiddleware):
    """Выдаёт хендлерам сессию и закрывает транзакцию."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self._session_factory() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
            except Exception:
                await session.rollback()
                raise
            await session.commit()
            return result
