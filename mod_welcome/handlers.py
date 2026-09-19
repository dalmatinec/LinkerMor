"""Приветствие новых участников (ТЗ §9)."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import JOIN_TRANSITION, ChatMemberUpdatedFilter, Command
from aiogram.types import ChatMemberUpdated, Message
from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import Role
from guards.chat_type import InGroup
from guards.module_enabled import ModuleEnabled
from guards.role import HasRole
from mod_triggers.content import UnsupportedContent
from mod_welcome.service import WelcomeService
from sender.sender import Sender
from settings.service import SettingsService
from texts.placeholders import chat_values, user_values
from texts.service import TextService

router = Router(name="welcome")

ADMIN_COMMAND = (InGroup(), ModuleEnabled("welcome"), HasRole(Role.CHAT_ADMIN))


@router.chat_member(
    InGroup(), ModuleEnabled("welcome"), ChatMemberUpdatedFilter(JOIN_TRANSITION)
)
async def on_join(
    event: ChatMemberUpdated,
    session: AsyncSession,
    settings: SettingsService,
    texts: TextService,
    sender: Sender,
) -> None:
    """Поприветствовать вошедшего.

    Если в чате включена проверка при входе, приветствие откладывается:
    его отправит модуль проверки после её прохождения. Иначе человек
    получил бы приветствие, не имея возможности ответить.
    """
    if await settings.get(event.chat.id, "captcha.enabled"):
        return

    user = event.new_chat_member.user
    if user.is_bot:
        return

    await WelcomeService(session, settings, texts, sender).send(event.chat.id, user, event.chat)


@router.message(Command("setwelcome"), *ADMIN_COMMAND)
async def cmd_set_welcome(
    message: Message,
    session: AsyncSession,
    settings: SettingsService,
    texts: TextService,
    sender: Sender,
) -> None:
    """``/setwelcome`` ответом на сообщение — оно станет приветствием."""
    source = message.reply_to_message
    values = {**chat_values(message.chat), **user_values(message.from_user, prefix="admin")}

    if source is None:
        await sender.reply(message, await texts.render(message.chat.id, "welcome_needs_reply",
                                                       values))
        return

    service = WelcomeService(session, settings, texts, sender)
    try:
        await service.set_from_message(message.chat.id, source, message.from_user.id)
    except UnsupportedContent as exc:
        await sender.reply(
            message,
            await texts.render(message.chat.id, "welcome_invalid",
                               {**values, "reason": str(exc)}),
        )
        return

    await sender.reply(message, await texts.render(message.chat.id, "welcome_saved", values))


@router.message(Command("delwelcome"), *ADMIN_COMMAND)
async def cmd_delete_welcome(
    message: Message,
    session: AsyncSession,
    settings: SettingsService,
    texts: TextService,
    sender: Sender,
) -> None:
    """``/delwelcome`` — вернуть приветствие по умолчанию."""
    removed = await WelcomeService(session, settings, texts, sender).clear(message.chat.id)
    values = chat_values(message.chat)

    await sender.reply(
        message,
        await texts.render(
            message.chat.id, "welcome_deleted" if removed else "welcome_not_set", values
        ),
    )


@router.message(Command("welcome"), *ADMIN_COMMAND)
async def cmd_preview_welcome(
    message: Message,
    session: AsyncSession,
    settings: SettingsService,
    texts: TextService,
    sender: Sender,
) -> None:
    """``/welcome`` — показать приветствие так, как его увидит новичок."""
    await WelcomeService(session, settings, texts, sender).send(
        message.chat.id, message.from_user, message.chat
    )
