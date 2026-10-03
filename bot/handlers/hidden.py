"""Служебные команды для тех, кому они не положены.

Не админ, набравший /admin или /ban, не получает никакого ответа, а
команда не уходит ни в рабочую группу, ни пользователю: снаружи бот
выглядит так, будто этих команд нет.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

SERVICE_COMMANDS = ("admin", "panel", "cancel", "ban", "unban", "id", "setgroup")

router = Router(name="hidden")


@router.message(Command(*SERVICE_COMMANDS))
async def swallow(message: Message) -> None:
    pass
