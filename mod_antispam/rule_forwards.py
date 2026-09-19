"""Пересылки из посторонних источников.

По умолчанию пересылки запрещены целиком, а белый список разрешает
исключения. Обратный порядок — запрещать по списку — проигрывает всегда:
новый спам-канал появляется быстрее, чем его успевают внести.
"""

from __future__ import annotations

from typing import Any

from cache.backend import CacheBackend
from cache.keys import ChatEntity, chat_key
from mod_antispam.engine import Rule, RuleContext
from mod_antispam.models import ForwardSource
from mod_antispam.repo import ForwardRepository
from sqlalchemy.ext.asyncio import AsyncSession

WHITELIST_CACHE_TTL = 600


def origin_of(message) -> tuple[str, int, str] | None:  # noqa: ANN001
    """Определить источник пересылки.

    Returns:
        Тип, идентификатор и название источника, либо ``None``, если
        сообщение не является пересылкой.
    """
    origin = message.forward_origin
    if origin is None:
        return None

    sender_user = getattr(origin, "sender_user", None)
    if sender_user is not None:
        name = " ".join(filter(None, (sender_user.first_name, sender_user.last_name)))
        return ForwardSource.USER, sender_user.id, name or str(sender_user.id)

    chat = getattr(origin, "chat", None)
    if chat is not None:
        return ForwardSource.CHANNEL, chat.id, chat.title or str(chat.id)

    sender_chat = getattr(origin, "sender_chat", None)
    if sender_chat is not None:
        return ForwardSource.CHAT, sender_chat.id, sender_chat.title or str(sender_chat.id)

    # Отправитель скрыл себя: разрешить такой источник нельзя,
    # идентификатора у него нет.
    hidden_name = getattr(origin, "sender_user_name", "") or ""
    return ForwardSource.HIDDEN, 0, hidden_name


async def whitelist_of(
    session: AsyncSession, cache: CacheBackend, chat_id: int
) -> set[tuple[str, int]]:
    """Разрешённые источники чата."""
    key = chat_key(ChatEntity.FILTER_RULES, chat_id, "forwards")
    cached = await cache.get(key)
    if cached is not None:
        return cached

    allowed = await ForwardRepository(session).list_sources(chat_id)
    await cache.set(key, allowed, ttl=WHITELIST_CACHE_TTL)
    return allowed


class ForwardsRule(Rule):
    """Пересылка из источника вне белого списка."""

    name = "forwards"
    priority = 15
    text_key = "antispam_forward"

    async def detect(self, ctx: RuleContext) -> dict[str, Any] | None:
        message = ctx.message

        # Посты из привязанного канала Telegram пересылает сам: это часть
        # устройства обсуждений, а не действие участника.
        if message.is_automatic_forward:
            return None

        origin = origin_of(message)
        if origin is None:
            return None

        source_type, source_id, title = origin
        if source_type != ForwardSource.HIDDEN:
            allowed = await whitelist_of(ctx.session, ctx.cache, ctx.chat_id)
            if (source_type, source_id) in allowed:
                return None

        return {"reason": title, "user": title}
