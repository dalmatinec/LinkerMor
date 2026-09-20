"""Текст с форматированием: подстановка не должна разрушать разметку."""

from __future__ import annotations

from aiogram.types import MessageEntity

from texts.entities import (
    Entity,
    EntityText,
    index_to_utf16,
    utf16_length,
    utf16_to_index,
)

#: Идентификатор премиум-эмодзи.
EMOJI_ID = "5378621920176607009"


# ─── Позиции UTF-16 ──────────────────────────────────────────────────────────


def test_utf16_length_counts_astral_characters_as_two() -> None:
    assert utf16_length("abc") == 3
    assert utf16_length("🔥") == 2
    assert utf16_length("🔥abc") == 5


def test_position_conversion_round_trip() -> None:
    text = "🔥 Привет 🎯 мир"
    for index in range(len(text) + 1):
        assert utf16_to_index(text, index_to_utf16(text, index)) == index


def test_offsets_from_telegram_are_converted() -> None:
    """Telegram присылает позиции в UTF-16: эмодзи занимает две единицы."""
    text = "🔥 жирный"
    # Слово «жирный» начинается на позиции 3 в UTF-16 и на индексе 2 в Python.
    entity = MessageEntity(type="bold", offset=3, length=6)

    converted = EntityText.from_telegram(text, [entity])

    assert converted.entities[0].offset == 2
    assert converted.text[2:8] == "жирный"


def test_round_trip_through_telegram_preserves_offsets() -> None:
    text = "🔥 жирный текст"
    original = [MessageEntity(type="bold", offset=3, length=6)]

    _, restored = EntityText.from_telegram(text, original).to_telegram()

    assert restored[0].offset == 3
    assert restored[0].length == 6


# ─── Подстановка значений ────────────────────────────────────────────────────


def test_entity_after_placeholder_shifts() -> None:
    """Значение длиннее плейсхолдера — форматирование за ним сдвигается."""
    source = EntityText(
        text="Привет, {user}! Правила чата",
        entities=(Entity("bold", 16, 7),),  # «Правила»
    )

    result = source.render({"user": "Александр"})

    bold = result.entities[0]
    assert result.text[bold.offset : bold.end] == "Правила"


def test_entity_covering_placeholder_grows() -> None:
    """Жирный, охватывающий плейсхолдер, должен охватить и значение."""
    source = EntityText(text="Привет, {user}!", entities=(Entity("bold", 8, 6),))

    result = source.render({"user": "Александр"})

    bold = result.entities[0]
    assert result.text[bold.offset : bold.end] == "Александр"


def test_entity_before_placeholder_untouched() -> None:
    source = EntityText(text="Привет, {user}!", entities=(Entity("bold", 0, 6),))

    result = source.render({"user": "Александр"})

    assert result.entities[0].offset == 0
    assert result.entities[0].length == 6


def test_several_placeholders_shift_cumulatively() -> None:
    source = EntityText(
        text="{admin} забанил {user}: причина",
        entities=(Entity("italic", 24, 7),),  # «причина»
    )

    result = source.render({"admin": "Модератор", "user": "Нарушитель"})

    italic = result.entities[0]
    assert result.text == "Модератор забанил Нарушитель: причина"
    assert result.text[italic.offset : italic.end] == "причина"


def test_custom_emoji_survives_substitution() -> None:
    """Премиум-эмодзи не должен съехать после подстановки (ТЗ §15)."""
    source = EntityText(
        text="🔥 Добро пожаловать, {user}!",
        entities=(Entity("custom_emoji", 0, 1, custom_emoji_id=EMOJI_ID),),
    )

    result = source.render({"user": "Александр"})
    text, telegram_entities = result.to_telegram()

    emoji = telegram_entities[0]
    assert emoji.custom_emoji_id == EMOJI_ID
    assert emoji.offset == 0
    assert emoji.length == 2  # эмодзи занимает две единицы UTF-16
    assert text.startswith("🔥")


def test_custom_emoji_after_placeholder_keeps_its_symbol() -> None:
    source = EntityText(
        text="{user} получил ранг 🎯",
        entities=(Entity("custom_emoji", 20, 1, custom_emoji_id=EMOJI_ID),),
    )

    result = source.render({"user": "Александр"})
    emoji = result.entities[0]

    assert result.text[emoji.offset : emoji.end] == "🎯"


def test_unknown_placeholder_never_reaches_the_user() -> None:
    """Критерий приёмки §32.18."""
    source = EntityText(text="Привет, {unknown_key}!")

    result = source.render({})

    assert "{" not in result.text
    assert result.text == "Привет, !"


def test_missing_value_among_known_ones() -> None:
    source = EntityText(text="{user} → {reason}")

    result = source.render({"user": "Иван"})

    assert result.text == "Иван → "


def test_value_with_its_own_formatting_is_inserted() -> None:
    """Упоминание без username возможно только через entity text_mention."""
    mention = EntityText(text="Александр", entities=(Entity("text_mention", 0, 9, user_id=42),))
    source = EntityText(text="Привет, {mention}!")

    result = source.render({"mention": mention})

    inserted = result.entities[0]
    assert inserted.type == "text_mention"
    assert inserted.user_id == 42
    assert result.text[inserted.offset : inserted.end] == "Александр"


def test_value_keeps_formatting_together_with_surrounding_entity() -> None:
    source = EntityText(text="Привет, {mention}!", entities=(Entity("bold", 0, 6),))
    mention = EntityText(text="Аня", entities=(Entity("text_mention", 0, 3, user_id=7),))

    result = source.render({"mention": mention})

    kinds = {e.type for e in result.entities}
    assert kinds == {"bold", "text_mention"}
    bold = next(e for e in result.entities if e.type == "bold")
    assert result.text[bold.offset : bold.end] == "Привет"


def test_substituted_value_is_not_interpreted_as_markup() -> None:
    """Имя пользователя не должно превращаться в форматирование."""
    source = EntityText(text="Привет, {user}!")

    result = source.render({"user": "<b>взлом</b>"})

    assert result.text == "Привет, <b>взлом</b>!"
    assert result.entities == ()


def test_placeholder_inside_value_is_not_substituted_again() -> None:
    """Значение подставляется один раз: рекурсия невозможна."""
    source = EntityText(text="Имя: {user}")

    result = source.render({"user": "{admin}", "admin": "секрет"})

    assert result.text == "Имя: {admin}"


def test_astral_value_shifts_offsets_correctly() -> None:
    """Эмодзи в подставленном значении сдвигает позиции в UTF-16."""
    source = EntityText(text="{user} в игре", entities=(Entity("bold", 7, 5),))

    result = source.render({"user": "🔥Игрок"})
    text, telegram_entities = result.to_telegram()

    bold = telegram_entities[0]
    assert text[result.entities[0].offset : result.entities[0].end] == "в игр"
    # «🔥Игрок» — 6 символов Python, но 7 единиц UTF-16.
    assert bold.offset == 8


def test_text_without_placeholders_returns_itself() -> None:
    source = EntityText(text="Обычный текст", entities=(Entity("bold", 0, 7),))
    assert source.render({"user": "x"}) is source


def test_placeholders_are_discoverable() -> None:
    source = EntityText(text="{admin} забанил {user}: {reason}")
    assert source.placeholders() == {"admin", "user", "reason"}


# ─── Хранение и устойчивость ─────────────────────────────────────────────────


def test_storage_round_trip() -> None:
    source = EntityText(
        text="🔥 Привет",
        entities=(
            Entity("custom_emoji", 0, 1, custom_emoji_id=EMOJI_ID),
            Entity("text_link", 2, 6, url="https://example.org"),
        ),
    )

    restored = EntityText.from_storage(source.text, source.entities_json())

    assert restored == source


def test_entities_beyond_text_are_dropped() -> None:
    """Повреждённые данные не должны приводить к отказу Telegram."""
    result = EntityText(text="Коротко", entities=(Entity("bold", 100, 5),))
    assert result.entities == ()


def test_entities_are_trimmed_to_text_length() -> None:
    result = EntityText(text="Коротко", entities=(Entity("bold", 4, 50),))
    assert result.entities[0].length == 3


def test_empty_entity_is_dropped_after_substitution() -> None:
    """Форматирование, охватывавшее только исчезнувший плейсхолдер."""
    source = EntityText(text="a{user}b", entities=(Entity("bold", 1, 6),))

    result = source.render({"user": ""})

    assert result.text == "ab"
    assert result.entities == ()
