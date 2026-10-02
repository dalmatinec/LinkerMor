"""Бан и разбан по ID, поиск ID пользователя. Работает в группе и в личке."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from bot import texts, users
from bot.db import Database
from bot.filters import in_work_group, is_admin
from bot.settings import Settings

router = Router(name="moderation")


async def resolve_target(
    message: Message, command: CommandObject, db: Database, settings: Settings
) -> tuple[int | None, str | None]:
    """ID из аргумента (число или @username) либо из сообщения, на которое ответили."""
    args = (command.args or "").split(maxsplit=1)
    if args:
        head = args[0]
        rest = args[1] if len(args) > 1 else None
        if head.lstrip("-").isdigit():
            return int(head), rest
        if head.startswith("@"):
            found = await db.find_user_by_username(head)
            return (found.id if found else None), rest
    reason = command.args or None
    reply = message.reply_to_message
    if reply is not None:
        if settings.group_id is not None and message.chat.id == settings.group_id:
            link = await db.by_group_message(message.chat.id, reply.message_id)
            if link is not None:
                return link[0], reason
        if message.chat.type == "private" and reply.forward_from is not None:
            return reply.forward_from.id, reason
    return None, reason


@router.message(Command("ban"), is_admin)
async def ban(message: Message, command: CommandObject, db: Database, settings: Settings) -> None:
    user_id, reason = await resolve_target(message, command, db, settings)
    if user_id is None:
        await message.reply(texts.BAN_USAGE, parse_mode="HTML")
        return
    changed = await db.set_banned(user_id, True, reason)
    text = texts.BAN_DONE if changed else texts.BAN_ALREADY
    await message.reply(text.format(id=user_id), parse_mode="HTML")


@router.message(Command("unban"), is_admin)
async def unban(message: Message, command: CommandObject, db: Database, settings: Settings) -> None:
    user_id, _ = await resolve_target(message, command, db, settings)
    if user_id is None:
        await message.reply(texts.BAN_USAGE, parse_mode="HTML")
        return
    changed = await db.set_banned(user_id, False)
    text = texts.UNBAN_DONE if changed else texts.UNBAN_ALREADY
    await message.reply(text.format(id=user_id), parse_mode="HTML")


@router.message(Command("ban", "unban"), F.chat.type != "private")
async def ban_denied(message: Message) -> None:
    await message.reply(texts.NOT_ADMIN)


@router.message(Command("id"), in_work_group)
async def show_id(message: Message, db: Database) -> None:
    reply = message.reply_to_message
    link = await db.by_group_message(message.chat.id, reply.message_id) if reply else None
    if link is None:
        await message.reply(texts.ID_HINT, parse_mode="HTML")
        return
    user = await db.get_user(link[0])
    name = users.mention(user) if user else str(link[0])
    await message.reply(f"{name}\n🆔 <code>{link[0]}</code>", parse_mode="HTML")


# ---- кнопки под сообщениями в группе --------------------------------------

@router.callback_query(F.data.startswith("who:"))
async def who(call: CallbackQuery, db: Database) -> None:
    user = await db.get_user(int(call.data.split(":", 1)[1]))
    await call.answer(users.info(user) if user else "Пользователь не найден", show_alert=True)


@router.callback_query(F.data.regexp(r"^(ban|unban):-?\d+$"))
async def ban_button(call: CallbackQuery, db: Database, settings: Settings) -> None:
    if not settings.is_admin(call.from_user.id):
        await call.answer(texts.NOT_ADMIN, show_alert=True)
        return
    action, raw = call.data.split(":", 1)
    user_id = int(raw)
    await db.set_banned(user_id, action == "ban", f"кнопкой, {call.from_user.full_name}")
    user = await db.get_user(user_id)
    await call.answer(
        f"Забанен {user_id}. Разбан: /unban {user_id}" if action == "ban" else f"Разбанен {user_id}",
        show_alert=True,
    )
    try:
        await call.message.edit_reply_markup(reply_markup=users.keyboard(user))
    except Exception:  # noqa: BLE001 - кнопки обновятся у следующих сообщений
        pass
