"""Callback-данные панели владельца."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class BroadcastAction(CallbackData, prefix="obc"):
    """Подтверждение или отмена рассылки."""

    action: str  # send | cancel
