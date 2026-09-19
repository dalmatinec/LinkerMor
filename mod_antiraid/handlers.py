"""Обработка входов во время налёта (ТЗ §19)."""

from __future__ import annotations

from typing import Any

from aiogram import Bot, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.filters import JOIN_TRANSITION, ChatMemberUpdatedFilter, Command, CommandObject
from aiogram.types import ChatMemberUpdated, Message
from sqlalchemy.ext.asyncio import AsyncSession

from cache.backend import CacheBackend
from core.constants import Role
from core.logging import get_logger
from guards.chat_type import InGroup
from guards.module_enabled import ModuleEnabled
from guards.role import HasRole
from mod_antiraid.service import RaidAction, RaidService
from mod_moderation.models import PunishmentSource
from mod_moderation.service import ModerationService
from permissions.service import PermissionService
from resolver.user_resolver import Target, TargetSource
from sender.sender import Sender
from settings.service import SettingsService
from texts.placeholders import chat_values, user_values
from texts.service import TextService

log = get_logger(__name__)

router = Router(name="antiraid")


@router.chat_member(
    InGroup(), ModuleEnabled("antiraid"), ChatMemberUpdatedFilter(JOIN_TRANSITION)
)
async def on_join(
    event: ChatMemberUpdated,
    session: AsyncSession,
    bot: Bot,
    cache: CacheBackend,
    settings: SettingsService,
    permissions: PermissionService,
    texts: TextService,
    sender: Sender,
) -> None:
    """Учесть вход и, если идёт налёт, применить выбранную меру.

    При мере «проверка» обработка передаётся дальше: капча сделает своё
    дело сама. При остальных мерах цепочка останавливается — приветствовать
    того, кого только что выставили, незачем.
    """
    user = event.new_chat_member.user
    if user.is_bot:
        raise SkipHandler

    service = RaidService(session, cache, settings)
    status = await service.register_join(event.chat.id)

    if status.just_started and await settings.get(event.chat.id, "antiraid.notify"):
        values: dict[str, Any] = {"count": str(status.joins), "reason": status.action}
        values.update(chat_values(event.chat))
        await sender.send(
            event.chat.id, await texts.render(event.chat.id, "antiraid_started", values)
        )

    if not status.active or status.action == RaidAction.CAPTCHA:
        # Обычный вход либо проверка при входе — дальше работают
        # остальные модули.
        raise SkipHandler

    target = Target(
        id=user.id,
        display_name=" ".join(filter(None, (user.first_name, user.last_name))) or str(user.id),
        source=TargetSource.USER_ID,
        username=user.username,
    )
    moderation = ModerationService(session, bot, permissions, settings)

    if status.action == RaidAction.BAN:
        await moderation.ban(event.chat.id, None, target, reason="raid",
                             source=PunishmentSource.FILTER)
    elif status.action == RaidAction.KICK:
        await moderation.kick(event.chat.id, None, target, reason="raid",
                              source=PunishmentSource.FILTER)
    else:
        await moderation.mute(event.chat.id, None, target, reason="raid",
                              source=PunishmentSource.FILTER)

    log.info(
        "вход обработан во время налёта",
        extra={"chat_id": event.chat.id, "target_id": user.id, "action": status.action},
    )


@router.message(Command("raid", "rd"), InGroup(), ModuleEnabled("antiraid"),
                HasRole(Role.CHAT_ADMIN))
async def cmd_raid(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    cache: CacheBackend,
    settings: SettingsService,
    texts: TextService,
    sender: Sender,
) -> None:
    """``/raid [on|off]`` — состояние тревоги или ручное управление ею."""
    service = RaidService(session, cache, settings)
    argument = (command.args or "").strip().lower()
    values = {**chat_values(message.chat), **user_values(message.from_user, prefix="admin")}

    if argument in {"on", "вкл"}:
        action = await service.activate(message.chat.id, manual=True)
        values["reason"] = action
        key = "antiraid_manual_on"
    elif argument in {"off", "выкл"}:
        removed = await service.deactivate(message.chat.id)
        key = "antiraid_manual_off" if removed else "antiraid_status_off"
    else:
        active = await service.is_active(message.chat.id)
        values["reason"] = await service.action_for(message.chat.id) if active else ""
        key = "antiraid_status_on" if active else "antiraid_status_off"

    await sender.reply(message, await texts.render(message.chat.id, key, values))
