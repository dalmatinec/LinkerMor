"""Состояния диалогов владельца."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Broadcast(StatesGroup):
    """Рассылка по администраторам чатов."""

    #: Бот ждёт сообщение, которое будет разослано.
    awaiting_message = State()
    #: Сообщение получено, ждём подтверждения.
    awaiting_confirm = State()
