"""Состояния диалога админ-панели.

Состояние хранится в Redis, поэтому выбранный чат и начатое редактирование
переживают перезапуск бота.
"""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class AdminPanel(StatesGroup):
    """Шаги работы с панелью."""

    #: Обычная навигация по меню.
    browsing = State()
    #: Бот ждёт новое значение настройки.
    awaiting_setting_value = State()
    #: Бот ждёт новый текст — вместе с форматированием и премиум-эмодзи.
    awaiting_text = State()
