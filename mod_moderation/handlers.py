"""Команды модерации (ТЗ §7).

Все команды принимают цель тремя способами — ответом, упоминанием и
идентификатором — потому что разбор аргументов вынесен в ``UserResolver``.
Команды ``/kick`` нет намеренно: исключение доступно только как настраиваемое
действие капчи и фильтров.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import Role
from guards.chat_type import InGroup
from guards.module_enabled import ModuleEnabled
from guards.role import HasRole
from mod_moderation.service import ModerationResult, ModerationService
from permissions.service import PermissionService
from resolver.duration import DurationError, parse_duration
from resolver.user_resolver import Target, UserResolver, split_argument
from sender.sender import Sender
from settings.service import SettingsService
from texts.placeholders import chat_values, user_values
from texts.service import TextService

router = Router(name="moderation")

#: Фильтры, общие для всех команд модерации.
MODERATOR_COMMAND = (InGroup(), ModuleEnabled("moderation"), HasRole(Role.MODERATOR))


async def _target_and_rest(
    resolver: UserResolver, message: Message, args: str | None
) -> tuple[Target, str]:
    """Определить цель команды и вернуть остаток аргументов.

    Если команда — ответ на сообщение или содержит упоминание, цель берётся
    оттуда, а весь остаток считается причиной. Иначе целью считается первый
    аргумент.
    """
    mentioned = any(
        entity.type == "text_mention" for entity in (message.entities or [])
    )
    if message.reply_to_message is not None or mentioned:
        return await resolver.resolve(message), (args or "").strip()

    token, rest = split_argument(args)
    return await resolver.resolve(message, argument=token), rest


def _split_duration(rest: str) -> tuple[timedelta | None, str]:
    """Отделить срок от причины.

    ``2h спам`` → два часа и «спам». Если первое слово сроком не является,
    вся строка считается причиной — администратору не нужно помнить порядок
    аргументов.
    """
    token, remainder = split_argument(rest)
    if token is None:
        return None, ""
    try:
        return parse_duration(token), remainder
    except DurationError:
        return None, rest


async def _respond(
    message: Message,
    result: ModerationResult,
    texts: TextService,
    sender: Sender,
    settings: SettingsService,
) -> None:
    """Сообщить о результате и при необходимости убрать команду."""
    values: dict[str, Any] = dict(result.values)
    values.update(chat_values(message.chat))
    if message.from_user is not None:
        values.update(user_values(message.from_user, prefix="admin"))

    rendered = await texts.render(message.chat.id, result.text_key, values)
    await sender.reply(message, rendered)

    if await settings.get(message.chat.id, "core.delete_commands"):
        from mod_moderation.actions import ModerationActions

        await ModerationActions(message.bot).delete_message(message.chat.id, message.message_id)


def _service(
    session: AsyncSession, bot: Bot, permissions: PermissionService, settings: SettingsService
) -> ModerationService:
    return ModerationService(session, bot, permissions, settings)


@router.message(Command("ban"), *MODERATOR_COMMAND)
async def cmd_ban(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    bot: Bot,
    permissions: PermissionService,
    settings: SettingsService,
    texts: TextService,
    resolver: UserResolver,
    sender: Sender,
) -> None:
    """``/ban [цель] [срок] [причина]`` — заблокировать участника."""
    target, rest = await _target_and_rest(resolver, message, command.args)
    duration, reason = _split_duration(rest)

    result = await _service(session, bot, permissions, settings).ban(
        message.chat.id, message.from_user.id, target, reason, duration
    )
    await _respond(message, result, texts, sender, settings)


@router.message(Command("unban"), *MODERATOR_COMMAND)
async def cmd_unban(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    bot: Bot,
    permissions: PermissionService,
    settings: SettingsService,
    texts: TextService,
    resolver: UserResolver,
    sender: Sender,
) -> None:
    """``/unban [цель]`` — снять блокировку."""
    target, _ = await _target_and_rest(resolver, message, command.args)

    result = await _service(session, bot, permissions, settings).unban(
        message.chat.id, message.from_user.id, target
    )
    await _respond(message, result, texts, sender, settings)


@router.message(Command("mute"), *MODERATOR_COMMAND)
async def cmd_mute(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    bot: Bot,
    permissions: PermissionService,
    settings: SettingsService,
    texts: TextService,
    resolver: UserResolver,
    sender: Sender,
) -> None:
    """``/mute [цель] [срок] [причина]`` — запретить писать."""
    target, rest = await _target_and_rest(resolver, message, command.args)
    duration, reason = _split_duration(rest)

    result = await _service(session, bot, permissions, settings).mute(
        message.chat.id, message.from_user.id, target, reason, duration
    )
    await _respond(message, result, texts, sender, settings)


@router.message(Command("unmute"), *MODERATOR_COMMAND)
async def cmd_unmute(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    bot: Bot,
    permissions: PermissionService,
    settings: SettingsService,
    texts: TextService,
    resolver: UserResolver,
    sender: Sender,
) -> None:
    """``/unmute [цель]`` — снять ограничение."""
    target, _ = await _target_and_rest(resolver, message, command.args)

    result = await _service(session, bot, permissions, settings).unmute(
        message.chat.id, message.from_user.id, target
    )
    await _respond(message, result, texts, sender, settings)


@router.message(Command("warn"), *MODERATOR_COMMAND)
async def cmd_warn(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    bot: Bot,
    permissions: PermissionService,
    settings: SettingsService,
    texts: TextService,
    resolver: UserResolver,
    sender: Sender,
) -> None:
    """``/warn [цель] [причина]`` — предупреждение с наказанием по порогу."""
    target, reason = await _target_and_rest(resolver, message, command.args)

    result = await _service(session, bot, permissions, settings).warn(
        message.chat.id, message.from_user.id, target, reason
    )
    await _respond(message, result, texts, sender, settings)


@router.message(Command("unwarn"), *MODERATOR_COMMAND)
async def cmd_unwarn(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    bot: Bot,
    permissions: PermissionService,
    settings: SettingsService,
    texts: TextService,
    resolver: UserResolver,
    sender: Sender,
) -> None:
    """``/unwarn [цель]`` — снять последнее предупреждение."""
    target, _ = await _target_and_rest(resolver, message, command.args)

    result = await _service(session, bot, permissions, settings).unwarn(
        message.chat.id, message.from_user.id, target
    )
    await _respond(message, result, texts, sender, settings)


@router.message(Command("warns", "warnings"), *MODERATOR_COMMAND)
async def cmd_warns(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    bot: Bot,
    permissions: PermissionService,
    settings: SettingsService,
    texts: TextService,
    resolver: UserResolver,
    sender: Sender,
) -> None:
    """``/warns [цель]`` — сколько предупреждений действует."""
    target, _ = await _target_and_rest(resolver, message, command.args)

    result = await _service(session, bot, permissions, settings).warnings_of(
        message.chat.id, target
    )
    await _respond(message, result, texts, sender, settings)
