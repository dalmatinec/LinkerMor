"""Вложения определённых типов."""

from __future__ import annotations

from typing import Any

from mod_antispam.engine import Rule, RuleContext

#: Поля сообщения, соответствующие видам вложений.
MEDIA_FIELDS = (
    ("photo", "photo"),
    ("video", "video"),
    ("animation", "animation"),
    ("document", "document"),
    ("audio", "audio"),
    ("voice", "voice"),
    ("video_note", "video_note"),
    ("sticker", "sticker"),
)


class MediaRule(Rule):
    """Вложение из списка запрещённых в этом чате."""

    name = "media"
    priority = 60
    text_key = "antispam_media"

    async def detect(self, ctx: RuleContext) -> dict[str, Any] | None:
        forbidden = {
            kind.strip()
            for kind in str(
                await ctx.settings.get(ctx.chat_id, "antispam.media.types")
            ).split(",")
            if kind.strip()
        }
        if not forbidden:
            return None

        for field, kind in MEDIA_FIELDS:
            if getattr(ctx.message, field, None) is not None and kind in forbidden:
                return {"reason": kind}
        return None
