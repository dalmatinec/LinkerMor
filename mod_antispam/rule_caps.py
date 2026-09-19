"""Сообщения капсом."""

from __future__ import annotations

from typing import Any

from mod_antispam.engine import Rule, RuleContext


class CapsRule(Rule):
    """Слишком большая доля заглавных букв.

    Короткие сообщения не проверяются: «ОК» капсом не является проблемой.
    """

    name = "caps"
    priority = 40
    text_key = "antispam_caps"

    async def detect(self, ctx: RuleContext) -> dict[str, Any] | None:
        text = ctx.text
        letters = [char for char in text if char.isalpha()]

        min_length = int(await ctx.settings.get(ctx.chat_id, "antispam.caps.min_length"))
        if len(letters) < min_length:
            return None

        percent = int(await ctx.settings.get(ctx.chat_id, "antispam.caps.percent"))
        upper = sum(1 for char in letters if char.isupper())
        share = upper * 100 // len(letters)

        if share >= percent:
            return {"reason": f"{share}%", "count": str(share)}
        return None
