"""Подделки внешних зависимостей для тестов.

``aiogram.test_utils`` в дистрибутив не входит, а сервисам нужен узкий
набор методов бота — поэтому подделка минимальна и явна. Каждый вызов
записывается, чтобы тест мог проверить не только результат в базе, но и
то, что бот действительно обратился к Telegram.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class Call:
    """Записанное обращение к Telegram."""

    method: str
    kwargs: dict[str, Any] = field(default_factory=dict)


class FakeBot:
    """Бот, отвечающий заранее заданными результатами."""

    def __init__(
        self,
        administrators: list[Any] | None = None,
        *,
        error: Exception | None = None,
        bot_id: int = 999,
        chat_permissions: Any = None,
    ) -> None:
        self._administrators = administrators or []
        self._error = error
        self._chat_permissions = chat_permissions
        self.id = bot_id
        #: Все обращения к Telegram в порядке вызова.
        self.calls: list[Call] = []

    # ─── Совместимость с кодом, читающим имена методов ───────────────────────

    @property
    def call_names(self) -> list[str]:
        return [call.method for call in self.calls]

    def called(self, method: str) -> Call | None:
        for call in self.calls:
            if call.method == method:
                return call
        return None

    # ─── Методы Bot API ──────────────────────────────────────────────────────

    async def get_chat_administrators(self, chat_id: int) -> list[Any]:
        self.calls.append(Call("get_chat_administrators", {"chat_id": chat_id}))
        if self._error is not None:
            raise self._error
        return self._administrators

    async def ban_chat_member(
        self, chat_id: int, user_id: int, until_date: datetime | None = None
    ) -> bool:
        self.calls.append(
            Call("ban_chat_member", {"chat_id": chat_id, "user_id": user_id,
                                     "until_date": until_date})
        )
        if self._error is not None:
            raise self._error
        return True

    async def unban_chat_member(
        self, chat_id: int, user_id: int, only_if_banned: bool = True
    ) -> bool:
        self.calls.append(
            Call("unban_chat_member", {"chat_id": chat_id, "user_id": user_id,
                                       "only_if_banned": only_if_banned})
        )
        if self._error is not None:
            raise self._error
        return True

    async def restrict_chat_member(
        self,
        chat_id: int,
        user_id: int,
        permissions: Any,
        until_date: datetime | None = None,
    ) -> bool:
        self.calls.append(
            Call(
                "restrict_chat_member",
                {"chat_id": chat_id, "user_id": user_id, "permissions": permissions,
                 "until_date": until_date},
            )
        )
        if self._error is not None:
            raise self._error
        return True

    async def ban_chat_sender_chat(self, chat_id: int, sender_chat_id: int) -> bool:
        self.calls.append(
            Call("ban_chat_sender_chat", {"chat_id": chat_id, "sender_chat_id": sender_chat_id})
        )
        return True

    async def unban_chat_sender_chat(self, chat_id: int, sender_chat_id: int) -> bool:
        self.calls.append(
            Call("unban_chat_sender_chat", {"chat_id": chat_id, "sender_chat_id": sender_chat_id})
        )
        return True

    async def get_chat(self, chat_id: int) -> Any:
        self.calls.append(Call("get_chat", {"chat_id": chat_id}))

        class _Chat:
            permissions = self._chat_permissions

        return _Chat()

    async def delete_message(self, chat_id: int, message_id: int) -> bool:
        self.calls.append(Call("delete_message", {"chat_id": chat_id, "message_id": message_id}))
        return True
