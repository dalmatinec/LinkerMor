"""Команды владельца бота (ТЗ §2).

Доступны только тем, кто перечислен в ``OWNER_IDS``, и только в личке:
это единственная глобальная проверка прав во всём проекте.
"""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from core.backup import BackupService
from core.config import Settings
from core.constants import ChatStatus
from core.health import HealthService
from core.logging import get_logger
from guards.chat_type import InPrivate
from guards.role import IsOwner
from mod_chats.repo import ChatRepository, MemberRepository
from mod_owner.callbacks import BroadcastAction
from mod_owner.states import Broadcast
from sender.sender import Sender
from texts.entities import EntityText
from ui.buttons import ButtonSpec, build_inline, parse_style
from texts.service import TextService

log = get_logger(__name__)

router = Router(name="owner")

OWNER_COMMAND = (InPrivate(), IsOwner())


@router.message(Command("health", "status"), *OWNER_COMMAND)
async def cmd_health(
    message: Message,
    health: HealthService,
    session: AsyncSession,
    texts: TextService,
    sender: Sender,
) -> None:
    """``/health`` — проверить состояние прямо сейчас."""
    report = await health.check()
    counts = await ChatRepository(session).count_by_status()

    values = {
        "items": report.describe(),
        "count": str(counts.get(ChatStatus.ACTIVE, 0)),
        "reason": "" if report.ok else ", ".join(c.name for c in report.failed),
    }
    key = "owner_health_ok" if report.ok else "owner_health_failed"
    await sender.reply(message, await texts.render(None, key, values))


@router.message(Command("backup"), *OWNER_COMMAND)
async def cmd_backup(
    message: Message,
    bot: Bot,
    config: Settings,
    texts: TextService,
    sender: Sender,
) -> None:
    """``/backup`` — создать копию базы и получить её файлом."""
    await sender.reply(message, await texts.render(None, "owner_backup_started", {}))

    service = BackupService(config, bot)
    result = await service.create()

    if not result.ok:
        await sender.reply(
            message,
            await texts.render(None, "owner_backup_failed", {"reason": result.error}),
        )
        return

    delivered = await service.deliver(result, frozenset({message.from_user.id}))
    service.rotate(config.backup_keep)

    if not delivered.delivered:
        await sender.reply(
            message,
            await texts.render(
                None, "owner_backup_failed",
                {"reason": delivered.error or "не удалось отправить файл"},
            ),
        )
        return

    log.info("копия создана по команде", extra={"actor": message.from_user.id})


@router.message(Command("chats"), *OWNER_COMMAND)
async def cmd_chats(
    message: Message,
    session: AsyncSession,
    texts: TextService,
    sender: Sender,
) -> None:
    """``/chats`` — все подключённые чаты."""
    repo = ChatRepository(session)
    chats = await repo.list_by_status(ChatStatus.ACTIVE, limit=100)
    counts = await repo.count_by_status()

    if not chats:
        await sender.reply(message, await texts.render(None, "owner_chats_empty", {}))
        return

    listing = "\n".join(f"• {chat.title or chat.chat_id} ({chat.chat_id})" for chat in chats)
    values = {
        "items": listing,
        "count": str(counts.get(ChatStatus.ACTIVE, 0)),
        "reason": str(counts.get(ChatStatus.INACTIVE, 0)),
    }
    content = await texts.render(None, "owner_chats", values)
    await sender.reply(message, content if content.text else EntityText(text=listing))


# ─── Рассылка по администраторам ─────────────────────────────────────────────


@router.message(Command("bc", "broadcast"), *OWNER_COMMAND)
async def cmd_broadcast(
    message: Message,
    texts: TextService,
    sender: Sender,
    state: FSMContext,
) -> None:
    """``/bc`` — разослать сообщение администраторам чатов.

    Рассылка идёт в личку администраторам, а не в сами чаты: объявление
    о работе бота адресовано тем, кто им управляет, и участникам чатов
    оно не нужно.
    """
    await state.set_state(Broadcast.awaiting_message)
    await sender.reply(message, await texts.render(None, "owner_broadcast_prompt", {}))


@router.message(Broadcast.awaiting_message, *OWNER_COMMAND)
async def receive_broadcast(
    message: Message,
    session: AsyncSession,
    texts: TextService,
    sender: Sender,
    state: FSMContext,
) -> None:
    """Принять сообщение и показать, скольким оно уйдёт."""
    body = EntityText.from_telegram(
        message.text or message.caption, message.entities or message.caption_entities
    )
    if not body.text:
        await sender.reply(message, await texts.render(None, "owner_broadcast_empty", {}))
        return

    recipients = await MemberRepository(session).all_admin_user_ids()
    await state.update_data(
        broadcast_text=body.text,
        broadcast_entities=body.entities_json(),
    )
    await state.set_state(Broadcast.awaiting_confirm)

    confirm = await texts.render(None, "owner_broadcast_confirm", {"count": str(len(recipients))})
    keyboard = build_inline(
        [
            [
                ButtonSpec(
                    text=(await texts.render(None, "owner_broadcast_btn_send", {})).text,
                    callback_data=BroadcastAction(action="send").pack(),
                    style=parse_style("green"),
                ),
                ButtonSpec(
                    text=(await texts.render(None, "owner_broadcast_btn_cancel", {})).text,
                    callback_data=BroadcastAction(action="cancel").pack(),
                    style=parse_style("red"),
                ),
            ]
        ]
    )
    await sender.send(message.chat.id, confirm, reply_markup=keyboard)


@router.callback_query(BroadcastAction.filter(F.action == "cancel"), InPrivate(), IsOwner())
async def cancel_broadcast(
    callback: CallbackQuery,
    texts: TextService,
    state: FSMContext,
) -> None:
    await state.clear()
    answer = await texts.render(None, "owner_broadcast_cancelled", {})
    if callback.message is not None:
        text, entities = answer.to_telegram()
        await callback.message.edit_text(text, entities=entities)
    await callback.answer()


@router.callback_query(BroadcastAction.filter(F.action == "send"), InPrivate(), IsOwner())
async def send_broadcast(
    callback: CallbackQuery,
    session: AsyncSession,
    texts: TextService,
    sender: Sender,
    state: FSMContext,
) -> None:
    """Разослать подтверждённое сообщение."""
    data = await state.get_data()
    body = EntityText.from_storage(
        data.get("broadcast_text", ""), data.get("broadcast_entities", [])
    )
    await state.clear()

    if not body.text:
        await callback.answer()
        return

    recipients = await MemberRepository(session).all_admin_user_ids()
    delivered = 0
    for user_id in recipients:
        # Отправка идёт через общий ограничитель: рассылка не должна
        # упираться в лимиты Telegram и подводить остальные чаты.
        if await sender.send(user_id, body) is not None:
            delivered += 1

    log.info(
        "рассылка выполнена",
        extra={"actor": callback.from_user.id, "recipients": len(recipients),
               "delivered": delivered},
    )

    report = await texts.render(
        None, "owner_broadcast_done",
        {"count": str(delivered), "reason": str(len(recipients) - delivered)},
    )
    if callback.message is not None:
        text, entities = report.to_telegram()
        await callback.message.edit_text(text, entities=entities)
    await callback.answer()
