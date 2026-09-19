"""Частота сообщений."""

from __future__ import annotations

from typing import Any

from cache.keys import ChatEntity, chat_key
from mod_antispam.engine import Rule, RuleContext


class FloodRule(Rule):
    """Слишком много сообщений за короткое время.

    Счётчик живёт в кеше со сроком жизни, равным окну наблюдения: хранить
    в базе историю сообщений ради этого не нужно, а текст сообщений не
    сохраняется вовсе.
    """

    name = "flood"
    priority = 30
    text_key = "antispam_flood"

    async def detect(self, ctx: RuleContext) -> dict[str, Any] | None:
        if not ctx.user_id:
            return None

        window = int(await ctx.settings.get(ctx.chat_id, "antispam.flood.window"))
        limit = int(await ctx.settings.get(ctx.chat_id, "antispam.flood.limit"))
        if window <= 0 or limit <= 0:
            return None

        key = chat_key(ChatEntity.FLOOD, ctx.chat_id, ctx.user_id)
        count = await ctx.cache.incr(key, ttl=window)

        if count > limit:
            return {"count": str(count), "duration": str(window)}
        return None
