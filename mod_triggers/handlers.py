"""Команды и срабатывание триггеров (ТЗ §8).

Ответ триггера не мешает остальным системам: команда обрабатывается своим
модулем раньше, а сюда попадают только обычные сообщения. Сообщения,
начинающиеся со слэша, пропускаются явно — иначе опечатка в команде
вызывала бы случайный триггер.
"""

from __future__ import annotations

from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from cache.backend import CacheBackend
from core.constants import Role
from core.errors import LinkerMorError
from core.logging import get_logger
from guards.chat_type import InGroup
from guards.module_enabled import ModuleEnabled
from guards.role import HasRole
from mod_triggers.content import UnsupportedContent
from mod_triggers.matcher import TriggerPatternError
from mod_triggers.models import ContentKind
from mod_triggers.service import TriggerService
from permissions.service import PermissionService
from sender.sender import Sender
from settings.service import SettingsService
from texts.placeholders import chat_values, user_values
from texts.service import TextService
from ui.buttons import ButtonSpec, build_inline

log = get_logger(__name__)

router = Router(name="triggers")

ADMIN_COMMAND = (InGroup(), ModuleEnabled("triggers"), HasRole(Role.CHAT_ADMIN))


class TriggerArgumentError(LinkerMorError):
    """Команда вызвана без ключевого слова."""

    text_key = "trigger_no_key"


async def _reply(
    message: Message,
    texts: TextService,
    sender: Sender,
    key: str,
    values: dict[str, Any] | None = None,
) -> None:
    """Ответить текстом из системы текстов."""
    payload = dict(values or {})
    payload.update(chat_values(message.chat))
    if message.from_user is not None:
        payload.update(user_values(message.from_user, prefix="admin"))

    await sender.reply(message, await texts.render(message.chat.id, key, payload))


@router.message(Command("at", "addtrigger", "addtrig"), *ADMIN_COMMAND)
async def cmd_add_trigger(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    cache: CacheBackend,
    texts: TextService,
    sender: Sender,
    permissions: PermissionService,
) -> None:
    """``/addtrigger <ключ>`` ответом на сообщение — оно станет ответом."""
    key, _, inline_text = (command.args or "").partition("\n")
    key = key.strip()
    if not key:
        raise TriggerArgumentError("Не указано ключевое слово")

    source = message.reply_to_message
    if source is None and not inline_text.strip():
        await _reply(message, texts, sender, "trigger_needs_reply", {"trigger": key})
        return

    role = await permissions.role_of(message.chat.id, message.from_user.id)
    service = TriggerService(session, cache)

    try:
        await service.add(
            message.chat.id,
            key,
            source=source,
            text=inline_text.strip() or None,
            actor_id=message.from_user.id,
            actor_role=role,
        )
    except (TriggerPatternError, UnsupportedContent) as exc:
        await _reply(message, texts, sender, "trigger_invalid",
                     {"trigger": key, "reason": str(exc)})
        return

    await _reply(message, texts, sender, "trigger_created", {"trigger": key})


@router.message(Command("dt", "deltrigger", "deltrig"), *ADMIN_COMMAND)
async def cmd_delete_trigger(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    cache: CacheBackend,
    texts: TextService,
    sender: Sender,
) -> None:
    """``/deltrigger <ключ>`` — удалить триггер."""
    key = (command.args or "").strip()
    if not key:
        raise TriggerArgumentError("Не указано ключевое слово")

    removed = await TriggerService(session, cache).remove(message.chat.id, key)
    await _reply(
        message, texts, sender,
        "trigger_deleted" if removed else "trigger_not_found",
        {"trigger": key},
    )


@router.message(Command("lt", "triggers"), *ADMIN_COMMAND)
async def cmd_list_triggers(
    message: Message,
    session: AsyncSession,
    cache: CacheBackend,
    texts: TextService,
    sender: Sender,
) -> None:
    """``/triggers`` — список ключевых слов этого чата."""
    triggers = await TriggerService(session, cache).list_all(message.chat.id)
    if not triggers:
        await _reply(message, texts, sender, "trigger_list_empty")
        return

    listing = "\n".join(
        f"• {trigger.display_key}" + ("" if trigger.is_enabled else " (выключен)")
        for trigger in triggers
    )
    await _reply(
        message, texts, sender, "trigger_list",
        {"count": str(len(triggers)), "trigger": listing},
    )


@router.message(
    InGroup(),
    ModuleEnabled("triggers"),
    F.text | F.caption,
    ~F.text.startswith("/"),
)
async def on_message(
    message: Message,
    session: AsyncSession,
    cache: CacheBackend,
    texts: TextService,
    settings: SettingsService,
    sender: Sender,
) -> None:
    """Ответить, если сообщение совпало с ключевым словом."""
    if message.from_user is None or message.from_user.is_bot:
        raise SkipHandler

    body = message.text or message.caption or ""
    trigger = await TriggerService(session, cache).find(message.chat.id, body)
    if trigger is None:
        # Совпадения нет: сообщение идёт дальше к репутации и рангам.
        raise SkipHandler

    kind, response, file_id, keyboard = TriggerService.response_of(trigger)

    values: dict[str, Any] = {"trigger": trigger.display_key}
    values.update(chat_values(message.chat))
    values.update(user_values(message.from_user))
    rendered = response.render(values)

    markup = None
    if keyboard:
        markup = build_inline(
            [[ButtonSpec.from_dict(button) for button in row] for row in keyboard]
        )

    if kind == ContentKind.TEXT:
        await sender.reply(message, rendered, reply_markup=markup)
    else:
        await sender.send_media(
            message.chat.id,
            kind,
            file_id,
            rendered,
            reply_markup=markup,
            reply_to_message_id=message.message_id,
            message_thread_id=message.message_thread_id,
        )

    log.debug(
        "сработал триггер",
        extra={"chat_id": message.chat.id, "trigger": trigger.key, "kind": kind},
    )
