"""Кнопки: нативные style и icon_custom_emoji_id (ТЗ §16, §18)."""

from __future__ import annotations

import pytest
from aiogram.enums import ButtonStyle

from ui.buttons import (
    ButtonSpec,
    ButtonSpecError,
    build_inline,
    chunk,
    parse_style,
)


def test_colors_map_to_native_styles() -> None:
    """Синий, зелёный и красный из ТЗ — это нативные стили Telegram."""
    assert parse_style("blue") is ButtonStyle.PRIMARY
    assert parse_style("green") is ButtonStyle.SUCCESS
    assert parse_style("red") is ButtonStyle.DANGER
    assert parse_style(None) is None


def test_native_style_names_accepted() -> None:
    assert parse_style("danger") is ButtonStyle.DANGER
    assert parse_style("SUCCESS") is ButtonStyle.SUCCESS


def test_unknown_style_rejected() -> None:
    with pytest.raises(ButtonSpecError):
        parse_style("фиолетовый")


def test_button_renders_style_and_custom_emoji() -> None:
    spec = ButtonSpec(
        text="Подтвердить",
        callback_data="mod:ban:ok",
        style=ButtonStyle.SUCCESS,
        icon_custom_emoji_id="5378621920176607009",
    )
    button = spec.to_aiogram()

    assert button.text == "Подтвердить"
    assert button.style == ButtonStyle.SUCCESS
    assert button.icon_custom_emoji_id == "5378621920176607009"


def test_round_trip_through_storage() -> None:
    """Кнопки хранятся в базе, поэтому сериализация обязана быть обратимой."""
    spec = ButtonSpec(
        text="Правила",
        url="https://example.org",
        style=ButtonStyle.PRIMARY,
        icon_custom_emoji_id="123",
    )
    assert ButtonSpec.from_dict(spec.to_dict()) == spec


def test_empty_fields_omitted_from_storage() -> None:
    spec = ButtonSpec(text="Меню", callback_data="menu")
    assert spec.to_dict() == {"text": "Меню", "callback_data": "menu"}


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"text": "  ", "callback_data": "x"}, "пустой текст"),
        ({"text": "A"}, "нет действия"),
        ({"text": "A", "callback_data": "x", "url": "https://e.org"}, "два действия"),
        ({"text": "A" * 65, "callback_data": "x"}, "текст длиннее лимита"),
        ({"text": "A", "callback_data": "я" * 40}, "callback_data больше 64 байт"),
    ],
)
def test_invalid_buttons_rejected(kwargs: dict, reason: str) -> None:
    with pytest.raises(ButtonSpecError):
        ButtonSpec(**kwargs)


def test_callback_limit_counts_bytes_not_characters() -> None:
    """64 — это байты UTF-8: кириллица занимает вдвое больше символов."""
    ButtonSpec(text="ok", callback_data="a" * 64)
    with pytest.raises(ButtonSpecError):
        ButtonSpec(text="ok", callback_data="a" * 65)


def test_with_text_keeps_appearance() -> None:
    """Подписи приходят из Custom Texts, оформление остаётся прежним."""
    spec = ButtonSpec(text="старый", callback_data="x", style=ButtonStyle.DANGER,
                      icon_custom_emoji_id="9")
    renamed = spec.with_text("новый")

    assert renamed.text == "новый"
    assert renamed.style is ButtonStyle.DANGER
    assert renamed.icon_custom_emoji_id == "9"


def test_chunk_layout() -> None:
    buttons = [ButtonSpec(text=str(i), callback_data=str(i)) for i in range(5)]
    assert [len(row) for row in chunk(buttons, 2)] == [2, 2, 1]
    with pytest.raises(ButtonSpecError):
        chunk(buttons, 0)


def test_build_inline_skips_empty_rows() -> None:
    markup = build_inline([[ButtonSpec(text="A", callback_data="a")], []])
    assert len(markup.inline_keyboard) == 1
