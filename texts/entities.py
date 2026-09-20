"""Текст с форматированием Telegram и корректной подстановкой значений.

Это центральный примитив системы текстов. Он решает задачу, на которой
обычно ломается поддержка форматирования: подстановка значений меняет длину
текста, а ``MessageEntity`` задаёт форматирование позициями внутри него.
Наивная замена ``text.replace(...)`` со старыми entity разрушает разметку —
жирный шрифт съезжает, премиум-эмодзи превращается в мусор.

Две тонкости, которые здесь учтены:

* **Offsets Telegram считаются в кодовых единицах UTF-16**, а Python
  индексирует строки по кодовым точкам. Для эмодзи и других символов вне
  базовой плоскости это разные числа. Внутри класса позиции хранятся в
  индексах Python, а преобразование выполняется на границе с Telegram.
* **Подставляемое значение само может нести форматирование.** Упоминание
  пользователя без username возможно только через entity ``text_mention``,
  поэтому значением плейсхолдера может быть не строка, а ``EntityText``.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Self

#: Плейсхолдер вида ``{user}``. Прочие фигурные скобки остаются как есть.
PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

#: Типы entity, у которых нет дополнительных полей.
SIMPLE_ENTITY_TYPES = frozenset(
    {
        "bold", "italic", "underline", "strikethrough", "spoiler", "code",
        "blockquote", "expandable_blockquote", "mention", "hashtag", "cashtag",
        "bot_command", "url", "email", "phone_number",
    }
)


# ─── Преобразование позиций ──────────────────────────────────────────────────


def utf16_length(text: str) -> int:
    """Длина строки в кодовых единицах UTF-16 — так её считает Telegram."""
    return sum(2 if ord(char) > 0xFFFF else 1 for char in text)


def _utf16_prefix(text: str) -> list[int]:
    """Накопительная длина в UTF-16 перед каждым символом строки."""
    prefix = [0]
    total = 0
    for char in text:
        total += 2 if ord(char) > 0xFFFF else 1
        prefix.append(total)
    return prefix


def utf16_to_index(text: str, offset: int) -> int:
    """Позиция Telegram → индекс символа Python."""
    prefix = _utf16_prefix(text)
    index = bisect_right(prefix, offset) - 1
    return max(0, min(index, len(text)))


def index_to_utf16(text: str, index: int) -> int:
    """Индекс символа Python → позиция Telegram."""
    return utf16_length(text[:index])


# ─── Entity ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Entity:
    """Фрагмент форматирования. ``offset`` и ``length`` — в символах Python."""

    type: str
    offset: int
    length: int
    url: str | None = None
    user_id: int | None = None
    language: str | None = None
    custom_emoji_id: str | None = None

    @property
    def end(self) -> int:
        return self.offset + self.length

    def to_dict(self) -> dict[str, Any]:
        """Представление для хранения в JSONB. Пустые поля опускаются."""
        data: dict[str, Any] = {"type": self.type, "offset": self.offset, "length": self.length}
        for key in ("url", "user_id", "language", "custom_emoji_id"):
            value = getattr(self, key)
            if value is not None:
                data[key] = value
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            type=data["type"],
            offset=int(data["offset"]),
            length=int(data["length"]),
            url=data.get("url"),
            user_id=data.get("user_id"),
            language=data.get("language"),
            custom_emoji_id=data.get("custom_emoji_id"),
        )


@dataclass(frozen=True, slots=True)
class EntityText:
    """Текст вместе с его форматированием."""

    text: str
    entities: tuple[Entity, ...] = field(default=())

    def __post_init__(self) -> None:
        # Entity, вышедшие за пределы текста, Telegram отвергает целиком.
        object.__setattr__(self, "entities", tuple(_sanitize(self.entities, len(self.text))))

    def __len__(self) -> int:
        return len(self.text)

    def __bool__(self) -> bool:
        return bool(self.text)

    # ─── Границы с Telegram ──────────────────────────────────────────────────

    @classmethod
    def from_telegram(cls, text: str | None, entities: list[Any] | None = None) -> Self:
        """Принять текст и entity, как их прислал Telegram."""
        text = text or ""
        converted: list[Entity] = []
        for raw in entities or []:
            start = utf16_to_index(text, raw.offset)
            end = utf16_to_index(text, raw.offset + raw.length)
            user = getattr(raw, "user", None)
            converted.append(
                Entity(
                    type=raw.type if isinstance(raw.type, str) else raw.type.value,
                    offset=start,
                    length=end - start,
                    url=getattr(raw, "url", None),
                    user_id=user.id if user is not None else None,
                    language=getattr(raw, "language", None),
                    custom_emoji_id=getattr(raw, "custom_emoji_id", None),
                )
            )
        return cls(text=text, entities=tuple(converted))

    def to_telegram(self) -> tuple[str, list[Any]]:
        """Отдать текст и entity с позициями в UTF-16, как ожидает Telegram."""
        from aiogram.types import MessageEntity, User

        result: list[MessageEntity] = []
        for entity in self.entities:
            offset = index_to_utf16(self.text, entity.offset)
            length = index_to_utf16(self.text, entity.end) - offset
            if length <= 0:
                continue
            result.append(
                MessageEntity(
                    type=entity.type,
                    offset=offset,
                    length=length,
                    url=entity.url,
                    user=(
                        User(id=entity.user_id, is_bot=False, first_name=" ")
                        if entity.user_id is not None
                        else None
                    ),
                    language=entity.language,
                    custom_emoji_id=entity.custom_emoji_id,
                )
            )
        return self.text, result

    # ─── Хранение ────────────────────────────────────────────────────────────

    def entities_json(self) -> list[dict[str, Any]]:
        return [entity.to_dict() for entity in self.entities]

    @classmethod
    def from_storage(cls, text: str, entities: list[dict[str, Any]] | None) -> Self:
        return cls(text=text, entities=tuple(Entity.from_dict(e) for e in entities or []))

    # ─── Подстановка значений ────────────────────────────────────────────────

    def placeholders(self) -> set[str]:
        """Имена всех плейсхолдеров, встречающихся в тексте."""
        return {match.group(1) for match in PLACEHOLDER_RE.finditer(self.text)}

    def render(self, values: Mapping[str, str | EntityText]) -> EntityText:
        """Подставить значения, сохранив форматирование.

        Неизвестные плейсхолдеры заменяются пустой строкой: пользователь
        никогда не должен увидеть ``{some_key}`` в сообщении (ТЗ §14).

        Значение подставляется как обычный текст и не интерпретируется как
        разметка, поэтому пользователь не может внедрить форматирование
        через собственное имя.
        """
        matches = list(PLACEHOLDER_RE.finditer(self.text))
        if not matches:
            return self

        parts: list[str] = []
        replacements: list[_Replacement] = []
        inserted: list[Entity] = []
        cursor = 0
        length_so_far = 0

        for match in matches:
            literal = self.text[cursor : match.start()]
            parts.append(literal)
            length_so_far += len(literal)

            value = values.get(match.group(1))
            if isinstance(value, EntityText):
                value_text, value_entities = value.text, value.entities
            elif value is None:
                value_text, value_entities = "", ()
            else:
                value_text, value_entities = str(value), ()

            parts.append(value_text)
            replacements.append(
                _Replacement(
                    old_start=match.start(),
                    old_end=match.end(),
                    new_start=length_so_far,
                    new_end=length_so_far + len(value_text),
                )
            )
            # Форматирование самого значения переезжает на новое место.
            inserted.extend(
                replace(entity, offset=entity.offset + length_so_far) for entity in value_entities
            )

            length_so_far += len(value_text)
            cursor = match.end()

        parts.append(self.text[cursor:])
        new_text = "".join(parts)

        moved = [
            replace(
                entity,
                offset=_remap(entity.offset, replacements, is_end=False),
                length=(
                    _remap(entity.end, replacements, is_end=True)
                    - _remap(entity.offset, replacements, is_end=False)
                ),
            )
            for entity in self.entities
        ]

        combined = sorted([*moved, *inserted], key=lambda e: (e.offset, e.type))
        return EntityText(text=new_text, entities=tuple(combined))


@dataclass(frozen=True, slots=True)
class _Replacement:
    """Участок, занятый плейсхолдером, и его место в новом тексте."""

    old_start: int
    old_end: int
    new_start: int
    new_end: int


def _remap(position: int, replacements: list[_Replacement], *, is_end: bool) -> int:
    """Перенести позицию из исходного текста в текст после подстановки.

    Позиция внутри плейсхолдера притягивается к краю подставленного
    значения: начало entity — к его началу, конец — к его концу. Так
    форматирование, захватившее плейсхолдер частично, остаётся осмысленным.
    """
    shift = 0
    for item in replacements:
        if position <= item.old_start:
            break
        if position >= item.old_end:
            shift += (item.new_end - item.new_start) - (item.old_end - item.old_start)
            continue
        return item.new_end if is_end else item.new_start
    return position + shift


def _sanitize(entities: tuple[Entity, ...], text_length: int) -> list[Entity]:
    """Отбросить пустые entity и подрезать вышедшие за границы текста."""
    result: list[Entity] = []
    for entity in entities:
        offset = max(0, entity.offset)
        end = min(entity.end, text_length)
        if end <= offset:
            continue
        result.append(replace(entity, offset=offset, length=end - offset))
    return result
