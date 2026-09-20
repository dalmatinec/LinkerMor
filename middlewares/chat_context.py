"""Контекст чата для каждого апдейта.

Middleware кладёт в данные хендлера запись чата и запись участника, а
заодно поддерживает справочник пользователей в актуальном состоянии.
Благодаря этому ни один хендлер не обращается к базе за тем, «кто и где»
прислал сообщение.

Ключевой принцип мультичатовости: контекст всегда привязан к конкретному
``chat_id``, глобального «текущего чата» в приложении не существует.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Chat as TgChat
from aiogram.types import TelegramObject, User as TgUser

from core.constants import ANONYMOUS_ADMIN_BOT_ID
from mod_chats.repo import ChatRepository, MemberRepository, UserRepository

#: Типы чатов, для которых ведётся контекст. В личке чата-арендатора нет.
GROUP_TYPES = frozenset({"group", "supergroup"})


class ChatContextMiddleware(BaseMiddleware):
    """Наполняет данные хендлера записями чата и участника."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        session = data.get("session")
        chat: TgChat | None = data.get("event_chat")
        user: TgUser | None = data.get("event_from_user")

        if session is None or chat is None:
            return await handler(event, data)

        # Сообщения анонимных администраторов приходят от служебного бота:
        # заводить его как пользователя не нужно.
        is_anonymous_admin = user is not None and user.id == ANONYMOUS_ADMIN_BOT_ID
        data["is_anonymous_admin"] = is_anonymous_admin

        if user is not None and not is_anonymous_admin and not user.is_bot:
            await UserRepository(session).upsert(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                is_bot=user.is_bot,
                is_premium=bool(getattr(user, "is_premium", False)),
                language_code=user.language_code,
            )

        if chat.type in GROUP_TYPES:
            data["chat_record"] = await ChatRepository(session).get(chat.id)
            if user is not None and not is_anonymous_admin:
                data["member"] = await MemberRepository(session).get(chat.id, user.id)

        return await handler(event, data)
