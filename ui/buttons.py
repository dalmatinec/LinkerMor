"""Описание кнопок и клавиатур (ТЗ §16, §18).

``ButtonSpec`` — собственная структура кнопки, независимая от aiogram.
Она нужна по двум причинам:

* кнопки настраиваются администраторами и хранятся в базе, поэтому им
  требуется стабильная сериализация, не завязанная на версию библиотеки;
* валидация (длина текста, лимит ``callback_data`` в 64 байта, ровно одно
  действие на кнопку) выполняется один раз здесь, а не в каждом модуле.

Нативные возможности Bot API 10.3 используются напрямую, без эмуляции:
``style`` задаёт цвет кнопки, ``icon_custom_emoji_id`` — премиум-эмодзи
перед текстом.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self

from aiogram.enums import ButtonStyle
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from core.constants import BUTTON_TEXT_MAX_LENGTH, CALLBACK_DATA_MAX_BYTES

#: Соответствие цветов из ТЗ нативным стилям Telegram.
COLOR_TO_STYLE: dict[str, ButtonStyle] = {
    "blue": ButtonStyle.PRIMARY,
    "green": ButtonStyle.SUCCESS,
    "red": ButtonStyle.DANGER,
}


class ButtonSpecError(ValueError):
    """Некорректное описание кнопки. Ловится при сохранении настроек."""


@dataclass(frozen=True, slots=True)
class ButtonSpec:
    """Одна кнопка inline-клавиатуры.

    Attributes:
        text: Подпись кнопки.
        callback_data: Данные callback. Взаимоисключающи с ``url``/``web_app_url``.
        url: Ссылка, открываемая по нажатию.
        web_app_url: Ссылка на Mini App.
        style: Цвет кнопки: ``primary`` (синий), ``success`` (зелёный),
            ``danger`` (красный). ``None`` — стиль темы клиента.
        icon_custom_emoji_id: Идентификатор премиум-эмодзи перед текстом.
    """

    text: str
    callback_data: str | None = None
    url: str | None = None
    web_app_url: str | None = None
    style: ButtonStyle | None = None
    icon_custom_emoji_id: str | None = None

    def __post_init__(self) -> None:
        if not self.text or not self.text.strip():
            raise ButtonSpecError("Текст кнопки не может быть пустым")
        if len(self.text) > BUTTON_TEXT_MAX_LENGTH:
            raise ButtonSpecError(
                f"Текст кнопки длиннее {BUTTON_TEXT_MAX_LENGTH} символов: {len(self.text)}"
            )

        actions = [self.callback_data, self.url, self.web_app_url]
        filled = [a for a in actions if a is not None]
        if len(filled) != 1:
            raise ButtonSpecError(
                "Кнопка должна иметь ровно одно действие: callback_data, url или web_app_url"
            )

        if self.callback_data is not None:
            size = len(self.callback_data.encode("utf-8"))
            if size > CALLBACK_DATA_MAX_BYTES:
                raise ButtonSpecError(
                    f"callback_data занимает {size} байт при лимите "
                    f"{CALLBACK_DATA_MAX_BYTES}: используйте токен вместо длинных данных"
                )

    # ─── Преобразования ──────────────────────────────────────────────────────

    def to_aiogram(self) -> InlineKeyboardButton:
        """Собрать объект кнопки для отправки в Telegram."""
        return InlineKeyboardButton(
            text=self.text,
            callback_data=self.callback_data,
            url=self.url,
            web_app=WebAppInfo(url=self.web_app_url) if self.web_app_url else None,
            style=self.style,
            icon_custom_emoji_id=self.icon_custom_emoji_id,
        )

    def to_dict(self) -> dict[str, Any]:
        """Представление для хранения в базе. Пустые поля опускаются."""
        data: dict[str, Any] = {"text": self.text}
        for key in ("callback_data", "url", "web_app_url", "icon_custom_emoji_id"):
            value = getattr(self, key)
            if value is not None:
                data[key] = value
        if self.style is not None:
            data["style"] = self.style.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Восстановить кнопку из базы, проверив её заново."""
        style = data.get("style")
        return cls(
            text=data["text"],
            callback_data=data.get("callback_data"),
            url=data.get("url"),
            web_app_url=data.get("web_app_url"),
            style=ButtonStyle(style) if style else None,
            icon_custom_emoji_id=data.get("icon_custom_emoji_id"),
        )

    def with_text(self, text: str) -> Self:
        """Копия кнопки с другой подписью: подписи приходят из Custom Texts."""
        return type(self)(
            text=text,
            callback_data=self.callback_data,
            url=self.url,
            web_app_url=self.web_app_url,
            style=self.style,
            icon_custom_emoji_id=self.icon_custom_emoji_id,
        )


def parse_style(value: str | None) -> ButtonStyle | None:
    """Принять как нативное имя стиля, так и цвет из ТЗ (blue/green/red)."""
    if value is None or value == "":
        return None
    normalized = value.strip().lower()
    if normalized in COLOR_TO_STYLE:
        return COLOR_TO_STYLE[normalized]
    try:
        return ButtonStyle(normalized)
    except ValueError as exc:
        allowed = ", ".join([*COLOR_TO_STYLE, *(s.value for s in ButtonStyle)])
        raise ButtonSpecError(f"Неизвестный стиль кнопки {value!r}. Допустимо: {allowed}") from exc


def build_inline(rows: list[list[ButtonSpec]]) -> InlineKeyboardMarkup:
    """Собрать inline-клавиатуру из строк кнопок."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[button.to_aiogram() for button in row] for row in rows if row]
    )


def chunk(buttons: list[ButtonSpec], per_row: int) -> list[list[ButtonSpec]]:
    """Разложить плоский список кнопок по строкам заданной ширины."""
    if per_row < 1:
        raise ButtonSpecError("В строке должна быть минимум одна кнопка")
    return [buttons[i : i + per_row] for i in range(0, len(buttons), per_row)]
