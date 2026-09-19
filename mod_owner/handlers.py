"""Команды владельца бота (ТЗ §2).

Доступны только тем, кто перечислен в ``OWNER_IDS``, и только в личке:
это единственная глобальная проверка прав во всём проекте.
"""

from __future__ import annotations

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from core.backup import BackupService
from core.config import Settings
from core.constants import ChatStatus
from core.health import HealthService
from core.logging import get_logger
from guards.chat_type import InPrivate
from guards.role import IsOwner
from mod_chats.repo import ChatRepository
from sender.sender import Sender
from texts.entities import EntityText
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
