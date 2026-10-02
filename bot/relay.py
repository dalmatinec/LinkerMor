"""Пересылка между пользователем и рабочей группой.

Сообщения копируются (``copyMessage``), а не пересылаются: копия сохраняет
форматирование, премиум-эмодзи и медиа, но не зависит от настроек
приватности отправителя. Кто написал, видно по кнопке под копией, а ответ
находит адресата по таблице соответствия, а не по имени в пересылке.
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import Message, ReactionTypeEmoji, ReplyParameters

from bot import stored, texts, users
from bot.db import Database, User
from bot.log import log
from bot.settings import Settings


def _reply_to(message_id: int | None) -> ReplyParameters | None:
    if message_id is None:
        return None
    return ReplyParameters(message_id=message_id, allow_sending_without_reply=True)


async def send_welcome(bot: Bot, settings: Settings, chat_id: int) -> None:
    welcome = settings["welcome"]
    if welcome:
        try:
            await stored.send(bot, chat_id, welcome)
            return
        except TelegramBadRequest as exc:
            # Например, file_id стал недействителен, не оставляем без ответа.
            log.warning("своё приветствие не отправилось: %s", exc)
    await bot.send_message(chat_id, texts.DEFAULT_WELCOME, parse_mode="HTML")


async def send_start_ad(bot: Bot, settings: Settings, chat_id: int) -> None:
    ad = settings["start_ad"]
    if not (settings["start_ad_on"] and ad):
        return
    try:
        await stored.send(bot, chat_id, ad)
    except TelegramBadRequest as exc:
        log.warning("реклама при старте не отправилась: %s", exc)


async def send_card(bot: Bot, db: Database, settings: Settings, user: User, new: bool) -> None:
    """Сообщить рабочей группе о нажатии /start."""
    group_id = settings.group_id
    if group_id is None:
        return
    try:
        sent = await bot.send_message(
            group_id, users.card(user, new), parse_mode="HTML",
            reply_markup=users.keyboard(user),
        )
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        log.error("рабочая группа недоступна: %s", exc)
        return
    await db.map_group_message(group_id, sent.message_id, user.id, None)


async def to_group(bot: Bot, db: Database, settings: Settings, message: Message, user: User) -> bool:
    """Скопировать сообщение пользователя в рабочую группу."""
    group_id = settings.group_id
    if group_id is None:
        return False

    # Пользователь отвечает на ответ сотрудника, продолжаем ту же ветку.
    reply_to = None
    if message.reply_to_message is not None:
        link = await db.by_user_message(user.id, message.reply_to_message.message_id)
        if link is not None and link[0] == group_id:
            reply_to = link[1]

    try:
        copy = await bot.copy_message(
            group_id, message.chat.id, message.message_id,
            reply_markup=users.keyboard(user),
            reply_parameters=_reply_to(reply_to),
        )
    except TelegramBadRequest as exc:
        log.warning("не удалось скопировать сообщение %s: %s", user.id, exc)
        return False
    except TelegramForbiddenError as exc:
        log.error("рабочая группа недоступна: %s", exc)
        return False
    await db.map_group_message(group_id, copy.message_id, user.id, message.message_id)
    return True


async def to_user(bot: Bot, db: Database, message: Message, user_id: int, user_msg_id: int | None) -> None:
    """Доставить ответ сотрудника пользователю и отметить это в группе."""
    group_id = message.chat.id
    try:
        copy = await bot.copy_message(
            user_id, group_id, message.message_id,
            reply_parameters=_reply_to(user_msg_id),
        )
    except TelegramForbiddenError:
        await db.set_blocked_bot(user_id)
        await message.reply(texts.REPLY_FAILED_BLOCKED.format(id=user_id), parse_mode="HTML")
        return
    except TelegramBadRequest as exc:
        await message.reply(
            texts.REPLY_FAILED.format(id=user_id, error=exc.message), parse_mode="HTML"
        )
        return

    await db.map_user_message(user_id, copy.message_id, group_id, message.message_id)
    # Реакция вместо сообщения "отправлено": видно всем в группе и не
    # тратит лимит сообщений в группу.
    try:
        await bot.set_message_reaction(group_id, message.message_id, [ReactionTypeEmoji(emoji="👍")])
    except TelegramBadRequest:
        pass  # реакции в группе выключены, ответ всё равно доставлен
