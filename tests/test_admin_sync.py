"""Синхронизация администраторов с Telegram (ТЗ §5)."""

from __future__ import annotations

from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import ChatMemberOwner
from aiogram.types import User as TgUser

from cache.keys import ChatEntity, chat_key
from cache.memory import MemoryCache
from core.constants import Role
from mod_chats.admin_sync import AdminSyncService
from mod_chats.repo import ChatRepository, MemberRepository
from tests.fakes import FakeBot
from tests.test_chat_lifecycle import admin_member

CHAT_ID = -1001111111111
OWNER_ID = 8243233601
ADMIN_ID = 555


async def _chat(session) -> None:
    await ChatRepository(session).upsert(
        chat_id=CHAT_ID, type_="supergroup", title="Чат", username=None,
        bot_status="administrator", bot_permissions={},
    )


def _administrators() -> list:
    owner = TgUser(id=OWNER_ID, is_bot=False, first_name="Создатель", username="creator")
    admin = TgUser(id=ADMIN_ID, is_bot=False, first_name="Админ", username="helper")
    return [
        ChatMemberOwner(user=owner, is_anonymous=False),
        admin_member(admin),
    ]


async def test_sync_writes_roles_from_telegram(session) -> None:
    await _chat(session)
    bot = FakeBot(_administrators())
    cache = MemoryCache()

    count = await AdminSyncService(session, bot, cache).sync(CHAT_ID, force=True)

    assert count == 2
    members = MemberRepository(session)
    owner = await members.get(CHAT_ID, OWNER_ID)
    admin = await members.get(CHAT_ID, ADMIN_ID)
    assert owner is not None and owner.role == Role.CHAT_OWNER
    assert admin is not None and admin.role == Role.CHAT_ADMIN


async def test_sync_result_is_cached_per_chat(session) -> None:
    """Вызов getChatAdministrators ограничен по частоте, результат кешируется."""
    await _chat(session)
    bot = FakeBot(_administrators())
    cache = MemoryCache()
    service = AdminSyncService(session, bot, cache)

    await service.sync(CHAT_ID, force=True)
    assert await cache.get(chat_key(ChatEntity.ADMINS, CHAT_ID)) == [ADMIN_ID, OWNER_ID]

    # Повторный вызов берёт данные из кеша и в Telegram не идёт.
    assert await service.sync(CHAT_ID) == 0
    assert bot.call_names == ["get_chat_administrators"]


async def test_sync_demotes_admins_removed_while_bot_was_offline(session) -> None:
    await _chat(session)
    members = MemberRepository(session)
    from mod_chats.repo import UserRepository

    await UserRepository(session).upsert(
        user_id=999, username="ex", first_name="Бывший", last_name=None
    )
    await members.upsert(chat_id=CHAT_ID, user_id=999, role=Role.CHAT_ADMIN,
                         tg_status="administrator")

    bot = FakeBot(_administrators())
    await AdminSyncService(session, bot, MemoryCache()).sync(CHAT_ID, force=True)
    session.expire_all()

    former = await members.get(CHAT_ID, 999)
    assert former is not None
    assert former.role == Role.MEMBER


async def test_sync_survives_api_failure(session) -> None:
    """Бота могли исключить между событиями — это не повод падать."""
    await _chat(session)
    bot = FakeBot(error=TelegramForbiddenError(method=None, message="бот исключён"))

    assert await AdminSyncService(session, bot, MemoryCache()).sync(CHAT_ID, force=True) == 0


async def test_invalidate_clears_only_its_chat(session) -> None:
    cache = MemoryCache()
    other_chat = -1002222222222
    await cache.set(chat_key(ChatEntity.ADMINS, CHAT_ID), [1])
    await cache.set(chat_key(ChatEntity.ADMINS, other_chat), [2])

    await AdminSyncService(session, FakeBot(), cache).invalidate(CHAT_ID)

    assert await cache.get(chat_key(ChatEntity.ADMINS, CHAT_ID)) is None
    assert await cache.get(chat_key(ChatEntity.ADMINS, other_chat)) == [2]
