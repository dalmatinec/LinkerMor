"""Ссылки и приглашения в другие чаты."""

from __future__ import annotations

import re
from typing import Any

from mod_antispam.engine import Rule, RuleContext

#: Ссылки на Telegram: приглашения и упоминания каналов.
TELEGRAM_LINK = re.compile(r"(?:t\.me|telegram\.me|telegram\.dog)/", re.IGNORECASE)

#: Типы entity, которыми Telegram размечает ссылки.
LINK_ENTITIES = frozenset({"url", "text_link"})


class LinksRule(Rule):
    """Сообщение содержит ссылку.

    Ссылки определяются по разметке Telegram, а не поиском по тексту:
    клиент уже распознал их, и обойти это подстановкой пробелов нельзя.
    """

    name = "links"
    priority = 20
    text_key = "antispam_links"

    async def detect(self, ctx: RuleContext) -> dict[str, Any] | None:
        message = ctx.message
        entities = (message.entities or []) + (message.caption_entities or [])

        only_telegram = bool(
            await ctx.settings.get(ctx.chat_id, "antispam.links.telegram_only")
        )

        for entity in entities:
            if entity.type not in LINK_ENTITIES:
                continue
            target = entity.url or ctx.text[entity.offset : entity.offset + entity.length]
            if not only_telegram or TELEGRAM_LINK.search(target or ""):
                return {"reason": target or ""}

        return None
