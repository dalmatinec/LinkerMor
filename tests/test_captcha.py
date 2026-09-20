"""Проверка при входе: состояние, гонки, исходы (ТЗ §10)."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import pytest
from aiogram.types import User as TgUser
from sqlalchemy import select

from cache.memory import MemoryCache
from mod_captcha.challenges import generate
from mod_captcha.models import CaptchaKind, CaptchaSession
from mod_captcha.service import CaptchaService, Verdict
from mod_chats.repo import ChatRepository
from mod_moderation.models import PunishmentSource, PunishmentType
from mod_moderation.repo import PunishmentRepository
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
def bot() -> FakeBot:
    return FakeBot()


@pytest.fixture
def settings(session, cache) -> SettingsService:
    return SettingsService(session, cache, build_settings(specs()))


def make_service(session, bot, cache, settings) -> CaptchaService:
    permissions = PermissionService(session, cache, frozenset(), bot_id=bot.id)
    moderation = ModerationService(session, bot, permissions, settings)
    return CaptchaService(session, settings, permissions, moderation, rng=random.Random(7))


async def setup(
    session, settings: SettingsService, chat_id: int = CHAT_A, *, can_restrict: bool = True
) -> None:
    await ChatRepository(session).upsert(
        chat_id=chat_id,
        type_="supergroup",
        title="Чат",
        username=None,
        bot_status="administrator",
        bot_permissions={"can_restrict_members": can_restrict},
    )
    await make_user(session, NEWCOMER.id, "newbie")
    await settings.set(chat_id, "captcha.enabled", True, ADMIN_ID)


# ─── Задания ─────────────────────────────────────────────────────────────────


def test_math_challenge_has_correct_answer_among_options() -> None:
    challenge = generate(CaptchaKind.MATH, rng=random.Random(1))
    left, right = challenge.question.split(" + ")

    assert challenge.answer == str(int(left) + int(right))
    assert challenge.answer in challenge.options
    assert len(challenge.options) == 4


def test_emoji_challenge_offers_the_named_symbol() -> None:
    challenge = generate(CaptchaKind.EMOJI, rng=random.Random(2))

    assert challenge.question == challenge.answer
    assert challenge.answer in challenge.options


def test_button_challenge_is_single_option() -> None:
    challenge = generate(CaptchaKind.BUTTON)
    assert challenge.options == ("ok",)


# ─── Запуск ──────────────────────────────────────────────────────────────────


async def test_start_creates_session_and_mutes(session, bot, cache, settings) -> None:
    await setup(session, settings)

    result = await make_service(session, bot, cache, settings).start(CHAT_A, NEWCOMER)

    assert result.started is True
    assert bot.called("restrict_chat_member") is not None
    stored = await session.get(CaptchaSession, (CHAT_A, NEWCOMER.id))
    assert stored is not None


async def test_disabled_captcha_does_nothing(session, bot, cache, settings) -> None:
    await setup(session, settings)
    await settings.set(CHAT_A, "captcha.enabled", False, ADMIN_ID)

    result = await make_service(session, bot, cache, settings).start(CHAT_A, NEWCOMER)

    assert result.started is False
    assert bot.calls == []


async def test_captcha_skipped_without_restrict_permission(
    session, bot, cache, settings
) -> None:
    """Без права ограничивать проверка бессмысленна: человек писал бы дальше."""
    await setup(session, settings, can_restrict=False)

    result = await make_service(session, bot, cache, settings).start(CHAT_A, NEWCOMER)

    assert result.started is False
    assert await session.get(CaptchaSession, (CHAT_A, NEWCOMER.id)) is None


async def test_second_join_event_does_not_restart_check(
    session, bot, cache, settings
) -> None:
    """Повторное событие входа не должно продлевать срок и обнулять попытки."""
    await setup(session, settings)
    service = make_service(session, bot, cache, settings)

    first = await service.start(CHAT_A, NEWCOMER)
    second = await service.start(CHAT_A, NEWCOMER)

    assert first.started is True
    assert second.started is False
    assert second.already_running is True


# ─── Ответы ──────────────────────────────────────────────────────────────────


async def test_correct_answer_passes_and_releases(session, bot, cache, settings) -> None:
    await setup(session, settings)
    service = make_service(session, bot, cache, settings)
    result = await service.start(CHAT_A, NEWCOMER)

    verdict, _ = await service.verify(CHAT_A, NEWCOMER.id, result.challenge.answer)

    assert verdict is Verdict.PASSED
    assert await session.get(CaptchaSession, (CHAT_A, NEWCOMER.id)) is None
    # Последним действием снят мут: у участника вернулись права.
    assert bot.call_names.count("restrict_chat_member") == 2


async def test_double_click_is_processed_once(session, bot, cache, settings) -> None:
    """Иначе второе нажатие привело бы к повторной выдаче приветствия."""
    await setup(session, settings)
    service = make_service(session, bot, cache, settings)
    result = await service.start(CHAT_A, NEWCOMER)

    first, _ = await service.verify(CHAT_A, NEWCOMER.id, result.challenge.answer)
    second, _ = await service.verify(CHAT_A, NEWCOMER.id, result.challenge.answer)

    assert first is Verdict.PASSED
    assert second is Verdict.MISSING


async def test_wrong_answer_decrements_attempts(session, bot, cache, settings) -> None:
    await setup(session, settings)
    service = make_service(session, bot, cache, settings)
    await service.start(CHAT_A, NEWCOMER)

    verdict, remaining = await service.verify(CHAT_A, NEWCOMER.id, "неверно")

    assert verdict is Verdict.WRONG
    assert remaining == 2


async def test_last_attempt_fails_and_punishes(session, bot, cache, settings) -> None:
    await setup(session, settings)
    await settings.set(CHAT_A, "captcha.attempts", 2, ADMIN_ID)
    await settings.set(CHAT_A, "captcha.fail_action", "kick", ADMIN_ID)
    service = make_service(session, bot, cache, settings)
    await service.start(CHAT_A, NEWCOMER)

    await service.verify(CHAT_A, NEWCOMER.id, "мимо")
    verdict, _ = await service.verify(CHAT_A, NEWCOMER.id, "мимо")

    assert verdict is Verdict.FAILED
    assert await session.get(CaptchaSession, (CHAT_A, NEWCOMER.id)) is None
    # Исключение с правом вернуться: бан и сразу снятие.
    assert bot.called("ban_chat_member") is not None
    assert bot.called("unban_chat_member") is not None


async def test_fail_action_ban_is_recorded(session, bot, cache, settings) -> None:
    await setup(session, settings)
    await settings.set(CHAT_A, "captcha.attempts", 1, ADMIN_ID)
    await settings.set(CHAT_A, "captcha.fail_action", "ban", ADMIN_ID)
    service = make_service(session, bot, cache, settings)
    await service.start(CHAT_A, NEWCOMER)

    await service.verify(CHAT_A, NEWCOMER.id, "мимо")

    stored = await PunishmentRepository(session).active(
        CHAT_A, NEWCOMER.id, PunishmentType.BAN
    )
    assert stored is not None
    assert stored.source == PunishmentSource.CAPTCHA


async def test_expired_check_is_reported(session, bot, cache, settings) -> None:
    await setup(session, settings)
    service = make_service(session, bot, cache, settings)
    result = await service.start(CHAT_A, NEWCOMER)

    stored = await session.get(CaptchaSession, (CHAT_A, NEWCOMER.id))
    stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.flush()

    verdict, _ = await service.verify(CHAT_A, NEWCOMER.id, result.challenge.answer)

    assert verdict is Verdict.EXPIRED


async def test_answer_without_session(session, bot, cache, settings) -> None:
    await setup(session, settings)

    verdict, _ = await make_service(session, bot, cache, settings).verify(
        CHAT_A, NEWCOMER.id, "ok"
    )

    assert verdict is Verdict.MISSING


# ─── Фоновая очистка ─────────────────────────────────────────────────────────


async def test_expired_sessions_are_collected(session, bot, cache, settings) -> None:
    """Без этого непрошедший проверку остался бы в муте навсегда."""
    await setup(session, settings)
    service = make_service(session, bot, cache, settings)
    await service.start(CHAT_A, NEWCOMER)

    stored = await session.get(CaptchaSession, (CHAT_A, NEWCOMER.id))
    stored.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await session.flush()

    expired = await service.collect_expired()

    assert [row.user_id for row in expired] == [NEWCOMER.id]


async def test_running_checks_are_not_collected(session, bot, cache, settings) -> None:
    await setup(session, settings)
    service = make_service(session, bot, cache, settings)
    await service.start(CHAT_A, NEWCOMER)

    assert await service.collect_expired() == []


# ─── Изоляция ────────────────────────────────────────────────────────────────


async def test_sessions_are_isolated_between_chats(session, bot, cache, settings) -> None:
    await setup(session, settings, CHAT_A)
    await setup(session, settings, CHAT_B)
    service = make_service(session, bot, cache, settings)

    await service.start(CHAT_A, NEWCOMER)

    rows = (await session.execute(select(CaptchaSession))).scalars().all()
    assert [row.chat_id for row in rows] == [CHAT_A]


async def test_captcha_type_is_per_chat(session, bot, cache, settings) -> None:
    await setup(session, settings, CHAT_A)
    await setup(session, settings, CHAT_B)
    await settings.set(CHAT_A, "captcha.type", "math", ADMIN_ID)
    service = make_service(session, bot, cache, settings)

    in_a = await service.start(CHAT_A, NEWCOMER)
    in_b = await service.start(CHAT_B, NEWCOMER)

    assert in_a.challenge.kind == CaptchaKind.MATH
    assert in_b.challenge.kind == CaptchaKind.BUTTON
