"""Подделки внешних зависимостей для тестов.

``aiogram.test_utils`` в дистрибутив не входит, а сервисам нужен лишь
узкий набор методов бота — поэтому подделка минимальна и явна.
"""

from __future__ import annotations

from typing import Any


class FakeBot:
    """Бот, отвечающий заранее заданными результатами.

    Записывает вызовы, чтобы тест мог проверить, ходил ли сервис в Telegram
    или обошёлся кешем.
    """

    def __init__(
        self,
        administrators: list[Any] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self._administrators = administrators or []
        self._error = error
        #: Имена вызванных методов в порядке обращения.
        self.calls: list[str] = []

    async def get_chat_administrators(self, chat_id: int) -> list[Any]:
        self.calls.append("get_chat_administrators")
        if self._error is not None:
            raise self._error
        return self._administrators
