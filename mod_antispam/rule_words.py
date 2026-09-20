"""Запрещённые слова."""

from __future__ import annotations

import re
from typing import Any

from cache.backend import CacheBackend
from cache.keys import ChatEntity, chat_key
from mod_antispam.engine import Rule, RuleContext
from mod_antispam.repo import WordRepository
from sqlalchemy.ext.asyncio import AsyncSession

WORDS_CACHE_TTL = 600


async def words_of(session: AsyncSession, cache: CacheBackend, chat_id: int) -> list[str]:
    """Список запрещённых слов чата. Проверяется на каждом сообщении."""
    key = chat_key(ChatEntity.FILTER_RULES, chat_id, "words")
    cached = await cache.get(key)
    if cached is not None:
        return cached

    words = await WordRepository(session).list_words(chat_id)
    await cache.set(key, words, ttl=WORDS_CACHE_TTL)
    return words


class WordsRule(Rule):
    """Сообщение содержит слово из списка чата."""

    name = "words"
    priority = 10
    text_key = "antispam_words"

    async def detect(self, ctx: RuleContext) -> dict[str, Any] | None:
        text = ctx.text
        if not text:
            return None

        words = await words_of(ctx.session, ctx.cache, ctx.chat_id)
        if not words:
            return None

        lowered = text.lower()
        strict = bool(await ctx.settings.get(ctx.chat_id, "antispam.words.whole_only"))

        for word in words:
            if strict:
                # По границам слова: «рак» не срабатывает в «ракета».
                if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", lowered):
                    return {"reason": word}
            elif word in lowered:
                return {"reason": word}

        return None
