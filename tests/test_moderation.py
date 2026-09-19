"""Модерация: бан, мут, предупреждения и их эскалация (ТЗ §7)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cache.memory import MemoryCache
from core.constants import Role
from core.errors import BotMissingPermission, PermissionDenied
from mod_chats.repo import ChatRepository, MemberRepository
from mod_moderation.models import PunishmentSource, PunishmentType
from mod_moderation.repo import PunishmentRepository, WarningRepository
from mod_moderation.service import ModerationService
from mod_moderation.spec import SETTINGS
from permissions.service import PermissionService
from resolver.user_resolver import Target, TargetSource
from settings.defs import CORE_SETTINGS, SettingsRegistry
from settings.service import SettingsService
from tests.fakes import FakeBot
from tests.test_chat_repository import make_user

CHAT_A = -1001111111111
CHAT_B = -1002222222222
ADMIN_ID = 8243233601
TARGET_ID = 555

TARGET = Target(id=TARGET_ID, display_name="Нарушитель", source=TargetSource.REPLY,
                username="spammer")


def registry() -> SettingsRegistry:
    return SettingsRegistry([*CORE_SETTINGS, *SETTINGS])


async def setup_chat(session, chat_id: int = CHAT_A, *, can_restrict: bool = True) -> None:
    await ChatRepository(session).upsert(
        chat_id=chat_id,
        type_="supergroup",
        title="Чат",
        username=None,
        bot_status="administrator",
        bot_permissions={"can_restrict_members": can_restrict, "can_delete_messages": True},
    )
    await make_user(session, ADMIN_ID, "admin")
    await make_user(session, TARGET_ID, "spammer")
    members = MemberRepository(session)
    await members.upsert(chat_id=chat_id, user_id=ADMIN_ID, role=Role.CHAT_ADMIN,
                         tg_status="administrator")
    await members.upsert(chat_id=chat_id, user_id=TARGET_ID, role=Role.MEMBER,
                         tg_status="member")


def make_service(session, bot: FakeBot, cache: MemoryCache) -> ModerationService:
    permissions = PermissionService(session, cache, frozenset(), bot_id=bot.id)
    settings = SettingsService(session, cache, registry())
    return ModerationService(session, bot, permissions, settings)


@pytest.fixture
def bot() -> FakeBot:
    return FakeBot()


@pytest.fixture
def cache() -> MemoryCache:
    return MemoryCache()


# ─── Блокировка ──────────────────────────────────────────────────────────────


async def test_ban_calls_telegram_and_records(session, bot, cache) -> None:
    await setup_chat(session)

    result = await make_service(session, bot, cache).ban(CHAT_A, ADMIN_ID, TARGET, "спам")

    assert result.text_key == "ban_success"
    assert bot.called("ban_chat_member") is not None
    stored = await PunishmentRepository(session).active(CHAT_A, TARGET_ID, PunishmentType.BAN)
    assert stored is not None
    assert stored.reason == "спам"
    assert stored.until is None


async def test_temporary_ban_sets_deadline(session, bot, cache) -> None:
    await setup_chat(session)

    await make_service(session, bot, cache).ban(
        CHAT_A, ADMIN_ID, TARGET, "спам", timedelta(hours=2)
    )

    stored = await PunishmentRepository(session).active(CHAT_A, TARGET_ID, PunishmentType.BAN)
    assert stored is not None and stored.until is not None
    assert bot.called("ban_chat_member").kwargs["until_date"] is not None


async def test_ban_without_bot_permission_is_refused(session, bot, cache) -> None:
    """Пользователь должен узнать о нехватке права, а не увидеть ошибку API."""
    await setup_chat(session, can_restrict=False)

    with pytest.raises(BotMissingPermission) as info:
        await make_service(session, bot, cache).ban(CHAT_A, ADMIN_ID, TARGET)

    assert info.value.permission == "can_restrict_members"
    assert bot.calls == []


async def test_cannot_ban_equal_admin(session, bot, cache) -> None:
    await setup_chat(session)
    await MemberRepository(session).upsert(
        chat_id=CHAT_A, user_id=TARGET_ID, role=Role.CHAT_ADMIN, tg_status="administrator"
    )

    with pytest.raises(PermissionDenied):
        await make_service(session, bot, cache).ban(CHAT_A, ADMIN_ID, TARGET)


async def test_repeated_ban_leaves_single_active_record(session, bot, cache) -> None:
    """Иначе снятие одной записи оставило бы человека наказанным по второй."""
    await setup_chat(session)
    service = make_service(session, bot, cache)

    await service.ban(CHAT_A, ADMIN_ID, TARGET, "первый")
    await service.ban(CHAT_A, ADMIN_ID, TARGET, "второй")

    history = await PunishmentRepository(session).history(CHAT_A, TARGET_ID)
    assert len(history) == 2
    assert len([p for p in history if p.is_active]) == 1


async def test_unban_clears_record(session, bot, cache) -> None:
    await setup_chat(session)
    service = make_service(session, bot, cache)
    await service.ban(CHAT_A, ADMIN_ID, TARGET)

    result = await service.unban(CHAT_A, ADMIN_ID, TARGET)

    assert result.text_key == "unban_success"
    assert await PunishmentRepository(session).active(CHAT_A, TARGET_ID, PunishmentType.BAN) is None


async def test_unban_uses_only_if_banned(session, bot, cache) -> None:
    """Без этого флага Telegram трактует вызов как приглашение в чат."""
    await setup_chat(session)

    await make_service(session, bot, cache).unban(CHAT_A, ADMIN_ID, TARGET)

    assert bot.called("unban_chat_member").kwargs["only_if_banned"] is True


async def test_channel_sender_is_banned_by_its_own_method(session, bot, cache) -> None:
    """Обычный бан на сообщение от имени канала не действует."""
    await setup_chat(session)
    channel = Target(id=-1005555555555, display_name="Канал", source=TargetSource.SENDER_CHAT,
                     is_chat=True)

    await make_service(session, bot, cache).ban(CHAT_A, ADMIN_ID, channel)

    assert bot.called("ban_chat_sender_chat") is not None
    assert bot.called("ban_chat_member") is None


# ─── Ограничение ─────────────────────────────────────────────────────────────


async def test_mute_records_and_restricts(session, bot, cache) -> None:
    await setup_chat(session)

    result = await make_service(session, bot, cache).mute(
        CHAT_A, ADMIN_ID, TARGET, "флуд", timedelta(hours=1)
    )

    assert result.text_key == "mute_success"
    call = bot.called("restrict_chat_member")
    assert call.kwargs["permissions"].can_send_messages is False
    assert await PunishmentRepository(session).active(CHAT_A, TARGET_ID, PunishmentType.MUTE)


async def test_unmute_restores_chat_defaults(session, bot, cache) -> None:
    """Возвращать все права подряд нельзя: в чате могут быть свои запреты."""
    from aiogram.types import ChatPermissions

    await setup_chat(session)
    bot_with_rules = FakeBot(chat_permissions=ChatPermissions(can_send_messages=True,
                                                              can_send_polls=False))
    service = make_service(session, bot_with_rules, cache)
    await service.mute(CHAT_A, ADMIN_ID, TARGET)

    await service.unmute(CHAT_A, ADMIN_ID, TARGET)

    restore = bot_with_rules.calls[-1]
    assert restore.kwargs["permissions"].can_send_polls is False


async def test_unmute_without_active_mute(session, bot, cache) -> None:
    await setup_chat(session)
    bot_fail = FakeBot(chat_permissions=None)

    result = await make_service(session, bot_fail, cache).unmute(CHAT_A, ADMIN_ID, TARGET)

    # Ограничение снято в Telegram, но записи не было — считаем успехом.
    assert result.text_key == "unmute_success"


# ─── Предупреждения ──────────────────────────────────────────────────────────


async def test_warn_counts_up(session, bot, cache) -> None:
    await setup_chat(session)
    service = make_service(session, bot, cache)

    first = await service.warn(CHAT_A, ADMIN_ID, TARGET, "мат")
    second = await service.warn(CHAT_A, ADMIN_ID, TARGET, "мат")

    assert first.values["warnings"] == "1"
    assert second.values["warnings"] == "2"
    assert second.text_key == "warn_success"


async def test_warn_limit_triggers_mute_and_resets(session, bot, cache) -> None:
    """Порог достигнут: применяется наказание, счёт начинается заново."""
    await setup_chat(session)
    service = make_service(session, bot, cache)

    for _ in range(2):
        await service.warn(CHAT_A, ADMIN_ID, TARGET, "мат")
    third = await service.warn(CHAT_A, ADMIN_ID, TARGET, "мат")

    assert third.text_key == "warn_limit_reached"
    assert bot.called("restrict_chat_member") is not None
    assert await WarningRepository(session).count_active(CHAT_A, TARGET_ID) == 0


async def test_warn_action_ban_is_respected(session, bot, cache) -> None:
    await setup_chat(session)
    settings = SettingsService(session, cache, registry())
    await settings.set(CHAT_A, "moderation.warn_action", "ban", ADMIN_ID)
    await settings.set(CHAT_A, "moderation.warn_limit", 1, ADMIN_ID)
    service = make_service(session, bot, cache)

    result = await service.warn(CHAT_A, ADMIN_ID, TARGET, "спам")

    assert result.text_key == "warn_limit_reached"
    assert bot.called("ban_chat_member") is not None
    stored = await PunishmentRepository(session).active(CHAT_A, TARGET_ID, PunishmentType.BAN)
    assert stored is not None and stored.source == PunishmentSource.WARN


async def test_unwarn_removes_last(session, bot, cache) -> None:
    await setup_chat(session)
    service = make_service(session, bot, cache)
    await service.warn(CHAT_A, ADMIN_ID, TARGET, "раз")
    await service.warn(CHAT_A, ADMIN_ID, TARGET, "два")

    result = await service.unwarn(CHAT_A, ADMIN_ID, TARGET)

    assert result.text_key == "unwarn_success"
    assert result.values["warnings"] == "1"


async def test_unwarn_without_warnings(session, bot, cache) -> None:
    await setup_chat(session)

    result = await make_service(session, bot, cache).unwarn(CHAT_A, ADMIN_ID, TARGET)

    assert result.text_key == "no_warnings"
    assert result.succeeded is False


async def test_expired_warnings_are_not_counted(session, bot, cache) -> None:
    """Нарушение полугодовой давности не должно вечно приближать к бану."""
    await setup_chat(session)
    warnings = WarningRepository(session)
    await warnings.add(
        chat_id=CHAT_A, user_id=TARGET_ID, actor_id=ADMIN_ID, reason="старое",
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    await warnings.add(
        chat_id=CHAT_A, user_id=TARGET_ID, actor_id=ADMIN_ID, reason="свежее",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )

    assert await warnings.count_active(CHAT_A, TARGET_ID) == 1


async def test_warnings_are_isolated_between_chats(session, bot, cache) -> None:
    """Критерий приёмки §32.8: предупреждения чата A не влияют на чат B."""
    await setup_chat(session, CHAT_A)
    await setup_chat(session, CHAT_B)
    service = make_service(session, bot, cache)

    await service.warn(CHAT_A, ADMIN_ID, TARGET, "мат")
    await service.warn(CHAT_A, ADMIN_ID, TARGET, "мат")

    warnings = WarningRepository(session)
    assert await warnings.count_active(CHAT_A, TARGET_ID) == 2
    assert await warnings.count_active(CHAT_B, TARGET_ID) == 0


async def test_warn_limit_setting_is_per_chat(session, bot, cache) -> None:
    """В чате A порог единица, в чате B — стандартный."""
    await setup_chat(session, CHAT_A)
    await setup_chat(session, CHAT_B)
    settings = SettingsService(session, cache, registry())
    await settings.set(CHAT_A, "moderation.warn_limit", 1, ADMIN_ID)
    service = make_service(session, bot, cache)

    in_a = await service.warn(CHAT_A, ADMIN_ID, TARGET, "мат")
    in_b = await service.warn(CHAT_B, ADMIN_ID, TARGET, "мат")

    assert in_a.text_key == "warn_limit_reached"
    assert in_b.text_key == "warn_success"


# ─── Истечение сроков ────────────────────────────────────────────────────────


async def test_expiration_task_closes_finished_punishments(session, bot, cache) -> None:
    """Telegram снимает ограничение сам — задача закрывает свою запись."""
    from tasks.expirations import close_expired_punishments

    await setup_chat(session)
    punishments = PunishmentRepository(session)
    await punishments.create(
        chat_id=CHAT_A, user_id=TARGET_ID, type_=PunishmentType.MUTE, actor_id=ADMIN_ID,
        reason="истёк", until=datetime.now(UTC) - timedelta(minutes=1),
    )

    closed = await close_expired_punishments(session)
    await session.flush()
    session.expire_all()

    assert closed == 1
    assert await punishments.active(CHAT_A, TARGET_ID, PunishmentType.MUTE) is None


async def test_expiration_task_keeps_running_punishments(session, bot, cache) -> None:
    from tasks.expirations import close_expired_punishments

    await setup_chat(session)
    await PunishmentRepository(session).create(
        chat_id=CHAT_A, user_id=TARGET_ID, type_=PunishmentType.MUTE, actor_id=ADMIN_ID,
        reason="идёт", until=datetime.now(UTC) + timedelta(hours=1),
    )

    assert await close_expired_punishments(session) == 0
