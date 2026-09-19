"""Ранги: показ, список и настройка ступеней (ТЗ §12)."""

from __future__ import annotations

from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cache.backend import CacheBackend
from core.constants import Role
from guards.chat_type import InGroup
from guards.module_enabled import ModuleEnabled
from guards.role import HasRole
from mod_ranks.service import RankService
from resolver.user_resolver import UserResolver, split_argument
from sender.sender import Sender
from settings.service import SettingsService
from texts.placeholders import chat_values, user_values
from texts.service import TextService

router = Router(name="ranks")

ADMIN_COMMAND = (InGroup(), ModuleEnabled("ranks"), HasRole(Role.CHAT_ADMIN))


@router.message(Command("rank"), InGroup(), ModuleEnabled("ranks"))
async def cmd_rank(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    cache: CacheBackend,
    settings: SettingsService,
    texts: TextService,
    sender: Sender,
    resolver: UserResolver,
    member: Any = None,
) -> None:
    """``/rank [цель]`` — текущая ступень и расстояние до следующей."""
    token, _ = split_argument(command.args)
    if message.reply_to_message is not None or token:
        target = await resolver.resolve(message, argument=token)
        user_id, name, own = target.id, target.display_name, False
    else:
        user_id = message.from_user.id
        name = message.from_user.first_name or str(user_id)
        own = True

    snapshot = await RankService(session, cache, settings).snapshot(
        message.chat.id, user_id, member if own else None
    )

    values: dict[str, Any] = {
        "user": name,
        "rank": snapshot.current.name if snapshot.current else "",
        "rank_name": snapshot.current.name if snapshot.current else "",
        "next_rank": snapshot.next_rank.name if snapshot.next_rank else "",
        "to_next_rank": str(snapshot.to_next),
        "count": str(snapshot.value),
    }
    values.update(chat_values(message.chat))

    key = "rank_show" if snapshot.current else "rank_none"
    await sender.reply(message, await texts.render(message.chat.id, key, values))


@router.message(Command("ranks"), InGroup(), ModuleEnabled("ranks"))
async def cmd_ranks(
    message: Message,
    session: AsyncSession,
    cache: CacheBackend,
    settings: SettingsService,
    texts: TextService,
    sender: Sender,
) -> None:
    """``/ranks`` — все ступени чата."""
    ranks = await RankService(session, cache, settings).ranks(message.chat.id)
    if not ranks:
        await sender.reply(
            message, await texts.render(message.chat.id, "rank_list_empty",
                                        chat_values(message.chat))
        )
        return

    listing = "\n".join(f"{rank.threshold} — {rank.name}" for rank in ranks)
    values = {**chat_values(message.chat), "items": listing, "count": str(len(ranks))}
    await sender.reply(message, await texts.render(message.chat.id, "rank_list", values))


@router.message(Command("addrank"), *ADMIN_COMMAND)
async def cmd_add_rank(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    cache: CacheBackend,
    settings: SettingsService,
    texts: TextService,
    sender: Sender,
) -> None:
    """``/addrank <порог> <название>`` — добавить ступень."""
    threshold_token, name = split_argument(command.args)
    values = {**chat_values(message.chat), **user_values(message.from_user, prefix="admin")}

    if threshold_token is None or not name.strip() or not threshold_token.lstrip("-").isdigit():
        await sender.reply(message, await texts.render(message.chat.id, "rank_usage", values))
        return

    values["rank"] = name.strip()
    values["count"] = threshold_token
    try:
        await RankService(session, cache, settings).add(
            message.chat.id, name.strip(), int(threshold_token)
        )
    except IntegrityError:
        # Порог или название уже заняты: иначе результат был бы
        # неопределённым при совпадении порогов.
        await session.rollback()
        await sender.reply(message, await texts.render(message.chat.id, "rank_exists", values))
        return

    await sender.reply(message, await texts.render(message.chat.id, "rank_added", values))


@router.message(Command("delrank"), *ADMIN_COMMAND)
async def cmd_delete_rank(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    cache: CacheBackend,
    settings: SettingsService,
    texts: TextService,
    sender: Sender,
) -> None:
    """``/delrank <название>`` — убрать ступень."""
    name = (command.args or "").strip()
    values = {**chat_values(message.chat), "rank": name}

    if not name:
        await sender.reply(message, await texts.render(message.chat.id, "rank_usage", values))
        return

    removed = await RankService(session, cache, settings).remove(message.chat.id, name)
    await sender.reply(
        message,
        await texts.render(message.chat.id, "rank_deleted" if removed else "rank_not_found",
                           values),
    )


@router.message(InGroup(), ModuleEnabled("ranks"), F.text | F.caption)
async def on_message(
    message: Message,
    session: AsyncSession,
    cache: CacheBackend,
    settings: SettingsService,
    texts: TextService,
    sender: Sender,
    member: Any = None,
) -> None:
    """Проверить ранг после сообщения, если он считается по активности."""
    user = message.from_user
    if user is None or user.is_bot or member is None:
        return

    metric = str(await settings.get(message.chat.id, "ranks.metric"))
    if metric == "reputation":
        # Сообщения на такой ранг не влияют: проверять нечего.
        return

    service = RankService(session, cache, settings)
    change = await service.sync(message.chat.id, user.id, member)
    if change is None or not await settings.get(message.chat.id, "ranks.notify"):
        return

    values: dict[str, Any] = {
        "old_rank": change.old_name,
        "new_rank": change.new_name,
        "rank": change.new_name,
        "rank_name": change.new_name,
        "count": str(change.value),
    }
    values.update(chat_values(message.chat))
    values.update(user_values(user))

    key = "rank_up" if change.direction == "up" else "rank_down"
    await sender.send(message.chat.id, await texts.render(message.chat.id, key, values))
