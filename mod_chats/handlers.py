"""Хендлеры подключения чатов.

Модуль обрабатывает только служебные события: появление бота в чате, смену
его прав, изменение статуса участников и переезд группы в супергруппу.
Пользовательских команд здесь нет.
"""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import ChatMemberUpdatedFilter
from aiogram.types import ChatMemberUpdated, Message
from sqlalchemy.ext.asyncio import AsyncSession

from cache.backend import CacheBackend
from cache.keys import chat_prefix
from core.logging import get_logger
from guards.chat_type import InGroup, IsMigration
from mod_chats.admin_sync import AdminSyncService
from mod_chats.lifecycle import ACTIVE_BOT_STATUSES, ChatLifecycleService

log = get_logger(__name__)

router = Router(name="chats")


@router.my_chat_member(InGroup(), ChatMemberUpdatedFilter(member_status_changed=True))
async def on_bot_status_changed(
    event: ChatMemberUpdated,
    session: AsyncSession,
    bot: Bot,
    cache: CacheBackend,
) -> None:
    """Бота добавили в чат, повысили, понизили или исключили (ТЗ §5)."""
    lifecycle = ChatLifecycleService(session)
    chat = await lifecycle.handle_bot_update(event)

    if chat is None:
        # Бот покинул чат: кеш этого чата больше не отражает реальность.
        await cache.delete_pattern(chat_prefix(event.chat.id))
        return

    # При подключении список администраторов берём сразу, не дожидаясь
    # событий: они приходят только при будущих изменениях.
    just_connected = event.old_chat_member.status not in ACTIVE_BOT_STATUSES
    await AdminSyncService(session, bot, cache).sync(chat.chat_id, force=just_connected)


@router.chat_member(InGroup())
async def on_member_status_changed(
    event: ChatMemberUpdated,
    session: AsyncSession,
    bot: Bot,
    cache: CacheBackend,
) -> None:
    """Участник вошёл, вышел или изменил права."""
    await ChatLifecycleService(session).handle_member_update(event)

    # Смена прав администратора делает кеш списка администраторов неверным.
    old_admin = event.old_chat_member.status in {"creator", "administrator"}
    new_admin = event.new_chat_member.status in {"creator", "administrator"}
    if old_admin != new_admin:
        await AdminSyncService(session, bot, cache).invalidate(event.chat.id)


@router.message(InGroup(), IsMigration())
async def on_chat_migrated(message: Message, session: AsyncSession, cache: CacheBackend) -> None:
    """Группа стала супергруппой и получила новый chat_id (ТЗ §5).

    Без переноса данных чат выглядел бы для бота как совершенно новый:
    настройки, репутация и предупреждения остались бы под старым ключом.
    """
    new_chat_id = message.migrate_to_chat_id
    if new_chat_id is None:  # pragma: no cover - отсечено фильтром
        return

    await ChatLifecycleService(session).handle_migration(
        old_chat_id=message.chat.id,
        new_chat_id=new_chat_id,
        chat=message.chat,
    )
    # Кеш под старым chat_id больше не нужен и может ввести в заблуждение.
    await cache.delete_pattern(chat_prefix(message.chat.id))


@router.message(InGroup(), F.text | F.caption)
async def on_group_message(
    message: Message,
    session: AsyncSession,
    **_: object,
) -> None:
    """Учёт активности участника.

    Счётчик нужен рангам: метрика ранга настраивается для каждого чата и
    может считаться по сообщениям. Инкремент атомарный.
    """
    user = message.from_user
    if user is None or user.is_bot:
        return

    from mod_chats.repo import MemberRepository

    members = MemberRepository(session)
    await members.ensure_exists(message.chat.id, user.id)
    await members.increment_messages(message.chat.id, user.id)
