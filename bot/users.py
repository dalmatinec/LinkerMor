"""Как бот показывает пользователя сотрудникам."""

from __future__ import annotations

from html import escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import texts
from bot.db import User


def mention(user: User) -> str:
    return f'<a href="tg://user?id={user.id}">{escape(user.full_name)}</a>'


def card(user: User, new: bool) -> str:
    head = texts.CARD_NEW if new else texts.CARD_REPEAT
    body = texts.CARD_BODY.format(
        name=mention(user),
        username=f"@{escape(user.username)}" if user.username else "нет",
        id=user.id,
    )
    return f"{head}\n{body}"


def info(user: User) -> str:
    """Текст для всплывающего окна (без разметки, до 200 символов)."""
    lines = [user.full_name, f"ID: {user.id}"]
    if user.username:
        lines.append(f"@{user.username}")
    if user.banned:
        lines.append("🚫 забанен" + (f": {user.ban_reason}" if user.ban_reason else ""))
    if user.blocked_bot:
        lines.append("остановил бота")
    return "\n".join(lines)[:200]


def keyboard(user: User) -> InlineKeyboardMarkup:
    """Кнопки под каждым сообщением пользователя в рабочей группе."""
    name = user.full_name
    if len(name) > 20:
        name = name[:20] + ".."
    ban = (
        InlineKeyboardButton(text="✅ Разбан", callback_data=f"unban:{user.id}")
        if user.banned
        else InlineKeyboardButton(text="🚫 Бан", callback_data=f"ban:{user.id}")
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text=f"👤 {name} · {user.id}", callback_data=f"who:{user.id}"),
            ban,
        ]]
    )
