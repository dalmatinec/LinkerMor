"""Сводка по чату (ТЗ §2)."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import Role
from guards.chat_type import InGroup
from guards.module_enabled import ModuleEnabled
from guards.role import HasRole
from mod_stats.service import StatsService
from sender.sender import Sender
from texts.placeholders import chat_values, user_values
from texts.service import TextService

router = Router(name="stats")


@router.message(
    Command("st", "stats"), InGroup(), ModuleEnabled("stats"), HasRole(Role.MODERATOR)
)
async def cmd_stats(
    message: Message,
    session: AsyncSession,
    texts: TextService,
    sender: Sender,
) -> None:
    """``/st`` — сводка по чату.

    Оформление задаётся текстом ``stats_report`` в панели: владелец может
    переставить строки, изменить формулировки и добавить премиум-эмодзи,
    не трогая код.
    """
    stats = await StatsService(session).collect(
        message.chat.id, message.chat.title or str(message.chat.id)
    )

    values = dict(stats.values)
    values.update(chat_values(message.chat))
    if message.from_user is not None:
        values.update(user_values(message.from_user, prefix="admin"))

    await sender.reply(message, await texts.render(message.chat.id, "stats_report", values))
