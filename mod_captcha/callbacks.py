"""Callback-данные проверки при входе."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class CaptchaAnswer(CallbackData, prefix="cap"):
    """Ответ на проверку.

    Идентификатор проверяемого входит в данные кнопки, чтобы отличить
    чужое нажатие. Это не замена проверке — она всё равно выполняется по
    отправителю, — а способ ответить человеку понятным сообщением.
    """

    user_id: int
    value: str
