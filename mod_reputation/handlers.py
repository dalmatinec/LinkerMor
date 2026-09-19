"""Начисление и показ репутации (ТЗ §11)."""

from __future__ import annotations

from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from cache.backend import CacheBackend
from core.logging import get_logger
from guards.chat_type import InGroup
from guards.module_enabled import ModuleEnabled
from mod_ranks.service import RankService
from mod_reputation.service import ReputationService
from mod_chats.repo import UserRepository
from resolver.user_resolver import UserResolver, split_argument
from sender.sender import Sender
from settings.service import SettingsService
from texts.placeholders import chat_values, user_values
from texts.service import TextService

log = get_logger(__name__)

router = Router(name="reputation")


def _words(raw: str) -> set[str]:
    """Разобрать список слов из настройки."""
    return {word.strip().lower() for word in raw.split(",") if word.strip()}


async def _notify_rank_change(
    message: Message,
    session: AsyncSession,
    cache: CacheBackend,
    settings: SettingsService,
    texts: TextService,
    sender: Sender,
    user_id: int,
    values: dict[str, Any],
) -> None:
    """Сообщить, если изменение репутации сменило ранг."""
    if not await settings.get(message.chat.id, "ranks.notify"):
        return

    member = None
    change = await RankService(session, cache, settings).sync(message.chat.id, user_id, member)
    if change is None:
        return

    payload = dict(values)
    payload.update(
        {
            "old_rank": change.old_name,
            "new_rank": change.new_name,
            "rank": change.new_name,
            "rank_name": change.new_name,
        }
    )
    key = "rank_up" if change.direction == "up" else "rank_down"
    await sender.send(message.chat.id, await texts.render(message.chat.id, key, payload))


@router.message(InGroup(), ModuleEnabled("reputation"), F.reply_to_message, F.text)
async def on_reputation_word(
    message: Message,
    session: AsyncSession,
    cache: CacheBackend,
    settings: SettingsService,
    texts: TextService,
    sender: Sender,
) -> None:
    """Изменить репутацию ответом со словом благодарности."""
    if not await settings.get(message.chat.id, "reputation.enabled"):
        return

    author = message.from_user
    target = message.reply_to_message.from_user
    if author is None or target is None or target.is_bot:
        return

    first_word = (message.text or "").strip().lower().split()[:1]
    if not first_word:
        return

    plus = _words(str(await settings.get(message.chat.id, "reputation.words_plus")))
    minus = _words(str(await settings.get(message.chat.id, "reputation.words_minus")))

    if first_word[0] in plus:
        delta = 1
    elif first_word[0] in minus:
        delta = -1
    else:
        return

    target_name = " ".join(filter(None, (target.first_name, target.last_name))) or str(target.id)
    result = await ReputationService(session, settings).change(
        message.chat.id, author.id, target.id, delta, target_name=target_name
    )

    values: dict[str, Any] = dict(result.values)
    values.update(chat_values(message.chat))
    values.update(user_values(target))
    values.update(user_values(author, prefix="admin"))

    await sender.reply(message, await texts.render(message.chat.id, result.text_key, values))

    if result.applied:
        await _notify_rank_change(
            message, session, cache, settings, texts, sender, target.id, values
        )


@router.message(Command("rep", "reputation"), InGroup(), ModuleEnabled("reputation"))
async def cmd_reputation(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    settings: SettingsService,
    texts: TextService,
    sender: Sender,
    resolver: UserResolver,
) -> None:
    """``/rep [цель]`` — показать репутацию."""
    token, _ = split_argument(command.args)
    if message.reply_to_message is not None or token:
        target = await resolver.resolve(message, argument=token)
        user_id, name = target.id, target.display_name
    else:
        user_id = message.from_user.id
        name = message.from_user.first_name or str(user_id)

    result = await ReputationService(session, settings).show(message.chat.id, user_id, name)
    values = {**result.values, **chat_values(message.chat)}

    await sender.reply(message, await texts.render(message.chat.id, result.text_key, values))


@router.message(Command("top"), InGroup(), ModuleEnabled("reputation"))
async def cmd_top(
    message: Message,
    session: AsyncSession,
    settings: SettingsService,
    texts: TextService,
    sender: Sender,
) -> None:
    """``/top`` — участники с наибольшей репутацией."""
    rows = await ReputationService(session, settings).top(message.chat.id)
    if not rows:
        await sender.reply(message, await texts.render(message.chat.id, "reputation_top_empty",
                                                       chat_values(message.chat)))
        return

    users = UserRepository(session)
    lines = []
    for position, (user_id, value) in enumerate(rows, start=1):
        stored = await users.get(user_id)
        name = stored.full_name if stored is not None else str(user_id)
        lines.append(f"{position}. {name} — {value}")

    values = {**chat_values(message.chat), "items": "\n".join(lines), "count": str(len(rows))}
    await sender.reply(message, await texts.render(message.chat.id, "reputation_top", values))
