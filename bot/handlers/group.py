"""Рабочая группа: ответы сотрудников уходят пользователям."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import Message

from bot import relay
from bot.db import Database
from bot.filters import in_work_group
from bot.log import log
from bot.settings import Settings

router = Router(name="group")
router.message.filter(in_work_group)


@router.message(F.migrate_to_chat_id)
async def migrated(message: Message, settings: Settings) -> None:
    """Группа стала супергруппой и получила новый ID."""
    log.info("рабочая группа %s стала %s", message.chat.id, message.migrate_to_chat_id)
    await settings.set("group_id", message.migrate_to_chat_id)


@router.message(F.reply_to_message)
async def staff_reply(message: Message, bot: Bot, db: Database) -> None:
    if message.from_user is None or message.from_user.is_bot:
        return
    link = await db.by_group_message(message.chat.id, message.reply_to_message.message_id)
    if link is None:
        return  # ответ на обычное сообщение коллеги, не наше дело
    user_id, user_msg_id = link
    await relay.to_user(bot, db, message, user_id, user_msg_id)
