"""Сохранённое сообщение: приветствие, реклама, рассылка.

Хранится не ссылка на сообщение админа, а его содержимое: тип, file_id,
текст и entities. Так приветствие не ломается, если админ удалит
исходное сообщение, а форматирование и премиум-эмодзи сохраняются
полностью — entities передаются Telegram как есть, без разметки.
"""

from __future__ import annotations

from typing import Any

from aiogram import Bot
from aiogram.types import Message, MessageEntity

# Тип -> (метод бота, имя параметра с файлом). Текст — особый случай.
MEDIA: dict[str, tuple[str, str]] = {
    "photo": ("send_photo", "photo"),
    "video": ("send_video", "video"),
    "animation": ("send_animation", "animation"),
    "document": ("send_document", "document"),
    "audio": ("send_audio", "audio"),
    "voice": ("send_voice", "voice"),
    "video_note": ("send_video_note", "video_note"),
    "sticker": ("send_sticker", "sticker"),
}
NO_CAPTION = {"video_note", "sticker"}


class UnsupportedMessage(ValueError):
    """Сообщение такого типа нельзя сохранить."""


def _entities(items: list[MessageEntity] | None) -> list[dict] | None:
    if not items:
        return None
    return [e.model_dump(mode="json", exclude_none=True) for e in items]


def from_message(message: Message) -> dict[str, Any]:
    """Снять содержимое сообщения в словарь, пригодный для JSON."""
    if message.text is not None:
        return {
            "type": "text",
            "text": message.text,
            "entities": _entities(message.entities),
        }
    for kind in MEDIA:
        media = getattr(message, kind)
        if media is None:
            continue
        file_id = media[-1].file_id if kind == "photo" else media.file_id
        return {
            "type": kind,
            "file_id": file_id,
            "text": message.caption,
            "entities": _entities(message.caption_entities),
            "above": bool(message.show_caption_above_media),
        }
    raise UnsupportedMessage(message.content_type)


def describe(stored: dict[str, Any] | None) -> str:
    """Короткое описание для админки."""
    if not stored:
        return "не задано"
    names = {
        "text": "текст", "photo": "фото", "video": "видео", "animation": "GIF",
        "document": "файл", "audio": "аудио", "voice": "голосовое",
        "video_note": "кружок", "sticker": "стикер",
    }
    kind = names.get(stored["type"], stored["type"])
    text = (stored.get("text") or "").strip().replace("\n", " ")
    if len(text) > 40:
        text = text[:40] + "…"
    return f"{kind}: {text}" if text else kind


async def send(bot: Bot, chat_id: int, stored: dict[str, Any], **kwargs: Any) -> Message:
    """Отправить сохранённое сообщение."""
    raw = stored.get("entities")
    entities = [MessageEntity(**e) for e in raw] if raw else None
    if stored["type"] == "text":
        return await bot.send_message(
            chat_id, stored["text"], entities=entities, parse_mode=None, **kwargs
        )
    method, param = MEDIA[stored["type"]]
    payload: dict[str, Any] = {param: stored["file_id"]}
    if stored["type"] not in NO_CAPTION:
        payload.update(caption=stored.get("text"), caption_entities=entities, parse_mode=None)
        if stored.get("above") and stored["type"] in {"photo", "video", "animation"}:
            payload["show_caption_above_media"] = True
    return await getattr(bot, method)(chat_id, **payload, **kwargs)
