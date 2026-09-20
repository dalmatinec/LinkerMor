"""Извлечение сообщения администратора в пригодный для хранения вид.

Администратор отвечает командой на сообщение, и это сообщение становится
ответом триггера. Сохранить нужно всё, что Telegram позволит отправить
обратно: вложение, подпись и её форматирование.
"""

from __future__ import annotations

from typing import Any

from aiogram.types import Message

from mod_triggers.models import ContentKind
from texts.entities import EntityText

#: Поля сообщения, содержащие вложение, и соответствующий им вид контента.
MEDIA_FIELDS: tuple[tuple[str, ContentKind], ...] = (
    ("photo", ContentKind.PHOTO),
    ("video", ContentKind.VIDEO),
    ("animation", ContentKind.ANIMATION),
    ("document", ContentKind.DOCUMENT),
    ("audio", ContentKind.AUDIO),
    ("voice", ContentKind.VOICE),
    ("video_note", ContentKind.VIDEO_NOTE),
    ("sticker", ContentKind.STICKER),
)


class UnsupportedContent(ValueError):
    """Такое сообщение сохранить нельзя."""


def extract(message: Message) -> dict[str, Any]:
    """Разобрать сообщение в поля для хранения.

    Raises:
        UnsupportedContent: в сообщении нет ни текста, ни поддерживаемого
            вложения.
    """
    body = EntityText.from_telegram(
        message.text or message.caption,
        message.entities or message.caption_entities,
    )

    for field, kind in MEDIA_FIELDS:
        value = getattr(message, field, None)
        if value is None:
            continue

        # У фотографии приходит список размеров: берём самый крупный.
        if field == "photo":
            value = value[-1]

        return {
            "kind": kind,
            "text": body.text or None,
            "entities": body.entities_json(),
            "file_id": value.file_id,
            "file_unique_id": value.file_unique_id,
        }

    if not body.text:
        raise UnsupportedContent("Сообщение не содержит ни текста, ни вложения")

    return {
        "kind": ContentKind.TEXT,
        "text": body.text,
        "entities": body.entities_json(),
        "file_id": None,
        "file_unique_id": None,
    }


def as_entity_text(content: Any) -> EntityText:
    """Собрать текст с форматированием из сохранённой записи."""
    return EntityText.from_storage(content.text or "", content.entities)
