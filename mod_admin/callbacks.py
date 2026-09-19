"""Callback-данные админ-панели (ТЗ §16).

Каждый модуль использует собственный префикс, поэтому нажатие в одной
панели не может попасть в обработчик другой.

Telegram ограничивает ``callback_data`` 64 байтами, а идентификатор чата
занимает до 14 символов. Поэтому выбранный чат хранится в состоянии
диалога, а в кнопки попадают только короткие значения. Это не ослабляет
проверку прав: она выполняется заново при каждом нажатии, а не берётся из
данных кнопки.
"""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class ChatChoice(CallbackData, prefix="ac"):
    """Выбор чата для настройки."""

    chat_id: int


class Nav(CallbackData, prefix="an"):
    """Переход между экранами панели."""

    #: ``root``, ``modules``, ``settings``, ``texts``, ``chats``
    screen: str
    page: int = 0


class ModuleAction(CallbackData, prefix="amd"):
    """Действие над модулем в этом чате."""

    module: str
    action: str  # open | toggle


class SettingAction(CallbackData, prefix="as"):
    """Действие над настройкой.

    ``key`` — часть ключа после точки: полный ключ собирается из модуля и
    её, чтобы уложиться в лимит размера.
    """

    module: str
    key: str
    action: str  # open | toggle | edit | reset


class TextAction(CallbackData, prefix="at"):
    """Действие над текстом."""

    module: str
    key: str
    action: str  # open | edit | reset
