"""Защита от массового входа."""

from __future__ import annotations

import pytest
from aiogram.types import User as TgUser
from sqlalchemy import select

from cache.keys import ChatEntity, chat_key
from cache.memory import MemoryCache
from mod_antiraid.models import RaidEvent
from mod_antiraid.service import RaidAction, RaidService
from mod_captcha.models import CaptchaSession
from mod_captcha.service import CaptchaService
from mod_chats.repo import ChatRepository
from mod_moderation.service import ModerationService
from permissions.service import PermissionService
from settings.defs import build_registry as build_settings
from settings.service import SettingsService
from tests.fakes import FakeBot
from tests.test_chat_repository import make_user

CHAT_A = -1001111111111
CHAT_B = -1002222222222
ADMIN_ID = 8243233601
NEWCOMER = TgUser(id=555, is_bot=False, first_name="Новичок", username="newbie")


def specs() -> list:
    from core.bootstrap import ENABLED_MODULES

    return ENABLED_MODULES()


@pytest.fixture
def cache() -> MemoryCache:
    return MemoryCache()


@pytest.fixture
def settings(session, cache) -> SettingsService:
    return SettingsService(session, cache, build_settings(specs()))


@pytest.fixture
def service(session, cache, settings) -> RaidService:
    return RaidService(session, cache, settings)


async def setup(session, chat_id: int = CHAT_A) -> None:
    await ChatRepository(session).upsert(
        chat_id=chat_id,
        type_="supergroup",
        title="Чат",
        username=None,
        bot_status="administrator",
        bot_permissions={"can_restrict_members": True},
    )
    await make_user(session, NEWCOMER.id, "newbie")


# ─── Обнаружение ─────────────────────────────────────────────────────────────


async def test_ordinary_joins_do_not_trigger(session, service, settings) -> None:
    await setup(session)
    await settings.set(CHAT_A, "antiraid.join_limit", 10, ADMIN_ID)

    for _ in range(9):
        status = await service.register_join(CHAT_A)

    assert status.active is False
    assert status.joins == 9


async def test_burst_of_joins_starts_the_alarm(session, service, settings) -> None:
    """Два десятка входов за полминуты почти всегда означают атаку."""
    await setup(session)
    await settings.set(CHAT_A, "antiraid.join_limit", 5, ADMIN_ID)

    statuses = [await service.register_join(CHAT_A) for _ in range(5)]

    assert statuses[-1].active is True
    assert statuses[-1].just_started is True
    assert await service.is_active(CHAT_A) is True


async def test_alarm_is_announced_only_once(session, service, settings) -> None:
    """Иначе чат завалит сообщениями о начале налёта."""
    await setup(session)
    await settings.set(CHAT_A, "antiraid.join_limit", 3, ADMIN_ID)

    starts = [
        (await service.register_join(CHAT_A)).just_started for _ in range(6)
    ]

    assert starts.count(True) == 1


async def test_raid_event_is_recorded(session, service, settings) -> None:
    """Без истории не понять, обстреливают ли чат регулярно."""
    await setup(session)
    await settings.set(CHAT_A, "antiraid.join_limit", 3, ADMIN_ID)

    for _ in range(3):
        await service.register_join(CHAT_A)

    events = (await session.execute(select(RaidEvent))).scalars().all()
    assert len(events) == 1
    assert events[0].chat_id == CHAT_A
    assert events[0].manual is False


async def test_disabled_module_never_triggers(session, service, settings) -> None:
    await setup(session)
    await settings.set(CHAT_A, "antiraid.enabled", False, ADMIN_ID)
    await settings.set(CHAT_A, "antiraid.join_limit", 3, ADMIN_ID)

    for _ in range(10):
        status = await service.register_join(CHAT_A)

    assert status.active is False


async def test_alarm_expires_on_its_own(session, cache, service, settings) -> None:
    """Тревога обязана заканчиваться сама, даже если бот перезапустится."""
    await setup(session)
    await settings.set(CHAT_A, "antiraid.join_limit", 3, ADMIN_ID)
    for _ in range(3):
        await service.register_join(CHAT_A)

    # Срок жизни записи в кеше и есть срок тревоги.
    await cache.delete(chat_key(ChatEntity.RAID, CHAT_A))

    assert await service.is_active(CHAT_A) is False


# ─── Ручное управление ───────────────────────────────────────────────────────


async def test_manual_activation(session, service) -> None:
    await setup(session)

    action = await service.activate(CHAT_A, manual=True)

    assert action == RaidAction.CAPTCHA
    assert await service.is_active(CHAT_A) is True
    events = (await session.execute(select(RaidEvent))).scalars().all()
    assert events[0].manual is True


async def test_manual_deactivation(session, service) -> None:
    await setup(session)
    await service.activate(CHAT_A, manual=True)

    assert await service.deactivate(CHAT_A) is True
    assert await service.deactivate(CHAT_A) is False


async def test_chosen_action_is_remembered(session, service, settings) -> None:
    """Смена настройки посреди налёта не должна менять меру на лету."""
    await setup(session)
    await settings.set(CHAT_A, "antiraid.action", "ban", ADMIN_ID)
    await service.activate(CHAT_A, manual=True)

    await settings.set(CHAT_A, "antiraid.action", "captcha", ADMIN_ID)

    assert await service.action_for(CHAT_A) == RaidAction.BAN


# ─── Изоляция ────────────────────────────────────────────────────────────────


async def test_alarm_is_per_chat(session, service, settings) -> None:
    await setup(session, CHAT_A)
    await setup(session, CHAT_B)
    await settings.set(CHAT_A, "antiraid.join_limit", 3, ADMIN_ID)

    for _ in range(3):
        await service.register_join(CHAT_A)

    assert await service.is_active(CHAT_A) is True
    assert await service.is_active(CHAT_B) is False


async def test_join_counters_are_per_chat(session, service, settings) -> None:
    await setup(session, CHAT_A)
    await setup(session, CHAT_B)
    await settings.set(CHAT_A, "antiraid.join_limit", 3, ADMIN_ID)
    await settings.set(CHAT_B, "antiraid.join_limit", 3, ADMIN_ID)

    for _ in range(2):
        await service.register_join(CHAT_A)
    status = await service.register_join(CHAT_B)

    assert status.joins == 1


# ─── Связь с проверкой при входе ─────────────────────────────────────────────


async def test_captcha_is_forced_during_raid(session, cache, settings) -> None:
    """Проверка нужна во время налёта, даже если обычно выключена."""
    await setup(session)
    assert await settings.get(CHAT_A, "captcha.enabled") is False

    bot = FakeBot()
    permissions = PermissionService(session, cache, frozenset(), bot_id=bot.id)
    moderation = ModerationService(session, bot, permissions, settings)
    captcha = CaptchaService(session, settings, permissions, moderation)

    without_raid = await captcha.start(CHAT_A, NEWCOMER)
    during_raid = await captcha.start(CHAT_A, NEWCOMER, force=True)

    assert without_raid.started is False
    assert during_raid.started is True
    assert await session.get(CaptchaSession, (CHAT_A, NEWCOMER.id)) is not None
