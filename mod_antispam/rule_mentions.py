"""Массовые упоминания участников."""

from __future__ import annotations

from typing import Any

from mod_antispam.engine import Rule, RuleContext

MENTION_ENTITIES = frozenset({"mention", "text_mention"})


class MentionsRule(Rule):
    """Слишком много упоминаний в одном сообщении.

    Типичный приём рассылки: перечислить два десятка участников, чтобы
    уведомление пришло каждому.
    """

    name = "mentions"
    priority = 50
    text_key = "antispam_mentions"

    async def detect(self, ctx: RuleContext) -> dict[str, Any] | None:
        message = ctx.message
        entities = (message.entities or []) + (message.caption_entities or [])
        count = sum(1 for entity in entities if entity.type in MENTION_ENTITIES)

        limit = int(await ctx.settings.get(ctx.chat_id, "antispam.mentions.limit"))
        if count > limit:
            return {"count": str(count)}
        return None
