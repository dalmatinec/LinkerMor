"""Репутация: начисление, ограничения, история (ТЗ §11)."""

from __future__ import annotations

import pytest

from cache.memory import MemoryCache
from mod_reputation.repo import ReputationRepository
from mod_reputation.service import ReputationService
from settings.defs import build_registry as build_settings
from settings.service import SettingsService
from tests.test_chat_repository import make_chat, make_user

CHAT_A = -1001111111111
CHAT_B = -1002222222222
GIVER = 8243233601
TAKER = 555
THIRD = 777


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
def service(session, settings) -> ReputationService:
    return ReputationService(session, settings)


async def setup(session, chat_id: int = CHAT_A) -> None:
    await make_chat(session, chat_id)
    for user_id in (GIVER, TAKER, THIRD):
        await make_user(session, user_id)


# ─── Начисление ──────────────────────────────────────────────────────────────


async def test_positive_change(session, service) -> None:
    await setup(session)

    result = await service.change(CHAT_A, GIVER, TAKER, 1, target_name="Кто-то")

    assert result.text_key == "reputation_given"
    assert result.value_after == 1


async def test_changes_accumulate(session, service, settings) -> None:
    await setup(session)
    await settings.set(CHAT_A, "reputation.cooldown", 0, GIVER)

    await service.change(CHAT_A, GIVER, TAKER, 1)
    result = await service.change(CHAT_A, THIRD, TAKER, 1)

    assert result.value_after == 2


async def test_history_is_recorded(session, service) -> None:
    """Спор о справедливости должен решаться фактами."""
    await setup(session)
    await service.change(CHAT_A, GIVER, TAKER, 1, reason="помог")

    history = await ReputationRepository(session).history(CHAT_A, TAKER)

    assert len(history) == 1
    assert history[0].actor_id == GIVER
    assert history[0].delta == 1
    assert history[0].value_after == 1
    assert history[0].reason == "помог"


async def test_negative_change(session, service) -> None:
    await setup(session)

    result = await service.change(CHAT_A, GIVER, TAKER, -1)

    assert result.text_key == "reputation_taken"
    assert result.value_after == -1


async def test_minus_can_be_disabled(session, service, settings) -> None:
    await setup(session)
    await settings.set(CHAT_A, "reputation.allow_minus", False, GIVER)

    result = await service.change(CHAT_A, GIVER, TAKER, -1)

    assert result.text_key == "reputation_minus_disabled"
    assert result.applied is False


# ─── Ограничения ─────────────────────────────────────────────────────────────


async def test_self_change_blocked(session, service) -> None:
    await setup(session)

    result = await service.change(CHAT_A, GIVER, GIVER, 1)

    assert result.text_key == "reputation_self"
    assert result.applied is False


async def test_cooldown_between_same_pair(session, service) -> None:
    """Без паузы двое участников накручивали бы репутацию по кругу."""
    await setup(session)

    first = await service.change(CHAT_A, GIVER, TAKER, 1)
    second = await service.change(CHAT_A, GIVER, TAKER, 1)

    assert first.applied is True
    assert second.text_key == "reputation_cooldown"


async def test_cooldown_does_not_affect_other_targets(session, service) -> None:
    await setup(session)
    await service.change(CHAT_A, GIVER, TAKER, 1)

    result = await service.change(CHAT_A, GIVER, THIRD, 1)

    assert result.applied is True


async def test_daily_limit(session, service, settings) -> None:
    await setup(session)
    await settings.set(CHAT_A, "reputation.cooldown", 0, GIVER)
    await settings.set(CHAT_A, "reputation.daily_limit", 2, GIVER)

    await service.change(CHAT_A, GIVER, TAKER, 1)
    await service.change(CHAT_A, GIVER, THIRD, 1)
    result = await service.change(CHAT_A, GIVER, TAKER, 1)

    assert result.text_key == "reputation_limit"


async def test_admin_action_ignores_limits(session, service) -> None:
    """Администратор правит репутацию командой, а не благодарностью."""
    await setup(session)
    await service.change(CHAT_A, GIVER, TAKER, 1)

    result = await service.change(CHAT_A, GIVER, TAKER, 5, enforce_limits=False)

    assert result.applied is True
    assert result.value_after == 6


# ─── Показ ───────────────────────────────────────────────────────────────────


async def test_top_is_ordered(session, service, settings) -> None:
    await setup(session)
    await settings.set(CHAT_A, "reputation.cooldown", 0, GIVER)
    await service.change(CHAT_A, GIVER, TAKER, 5, enforce_limits=False)
    await service.change(CHAT_A, GIVER, THIRD, 9, enforce_limits=False)

    top = await service.top(CHAT_A)

    assert top == [(THIRD, 9), (TAKER, 5)]


async def test_position_reflects_standing(session, service) -> None:
    await setup(session)
    await service.change(CHAT_A, GIVER, TAKER, 5, enforce_limits=False)
    await service.change(CHAT_A, GIVER, THIRD, 9, enforce_limits=False)

    result = await service.show(CHAT_A, TAKER, "Кто-то")

    assert result.values["position"] == "2"


# ─── Изоляция ────────────────────────────────────────────────────────────────


async def test_reputation_is_per_chat(session, service) -> None:
    """Критерий приёмки §32.8."""
    await setup(session, CHAT_A)
    await setup(session, CHAT_B)

    await service.change(CHAT_A, GIVER, TAKER, 1)

    assert await service.value_of(CHAT_A, TAKER) == 1
    assert await service.value_of(CHAT_B, TAKER) == 0


async def test_cooldown_is_per_chat(session, service) -> None:
    await setup(session, CHAT_A)
    await setup(session, CHAT_B)
    await service.change(CHAT_A, GIVER, TAKER, 1)

    result = await service.change(CHAT_B, GIVER, TAKER, 1)

    assert result.applied is True
