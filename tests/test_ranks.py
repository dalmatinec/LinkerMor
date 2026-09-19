"""Ранги: расчёт, переходы, влияние настроек на рантайм (ТЗ §12)."""

from __future__ import annotations

import pytest

from cache.keys import ChatEntity, chat_key
from cache.memory import MemoryCache
from mod_chats.repo import MemberRepository
from mod_ranks.models import Rank
from mod_ranks.service import RankService
from mod_reputation.service import ReputationService
from settings.defs import build_registry as build_settings
from settings.service import SettingsService
from tests.test_chat_repository import make_chat, make_user

CHAT_A = -1001111111111
CHAT_B = -1002222222222
ADMIN_ID = 8243233601
USER_ID = 555


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
def service(session, cache, settings) -> RankService:
    return RankService(session, cache, settings)


async def setup(session, chat_id: int = CHAT_A) -> None:
    await make_chat(session, chat_id)
    for user_id in (ADMIN_ID, USER_ID):
        await make_user(session, user_id)
    await MemberRepository(session).ensure_exists(chat_id, USER_ID)


async def make_ranks(service: RankService, chat_id: int = CHAT_A) -> None:
    await service.add(chat_id, "Новичок", 0)
    await service.add(chat_id, "Свой", 10)
    await service.add(chat_id, "Ветеран", 50)


# ─── Расчёт ступени ──────────────────────────────────────────────────────────


def test_rank_for_picks_highest_reached() -> None:
    ranks = [
        Rank(id=1, chat_id=CHAT_A, name="Новичок", threshold=0),
        Rank(id=2, chat_id=CHAT_A, name="Свой", threshold=10),
        Rank(id=3, chat_id=CHAT_A, name="Ветеран", threshold=50),
    ]

    assert RankService.rank_for(ranks, 0).name == "Новичок"
    assert RankService.rank_for(ranks, 9).name == "Новичок"
    assert RankService.rank_for(ranks, 10).name == "Свой"
    assert RankService.rank_for(ranks, 999).name == "Ветеран"


def test_rank_for_returns_none_below_all_thresholds() -> None:
    ranks = [Rank(id=1, chat_id=CHAT_A, name="Свой", threshold=10)]
    assert RankService.rank_for(ranks, 5) is None


def test_next_after_points_forward() -> None:
    ranks = [
        Rank(id=1, chat_id=CHAT_A, name="Свой", threshold=10),
        Rank(id=2, chat_id=CHAT_A, name="Ветеран", threshold=50),
    ]

    assert RankService.next_after(ranks, 10).name == "Ветеран"
    assert RankService.next_after(ranks, 60) is None


# ─── Метрика ─────────────────────────────────────────────────────────────────


async def test_metric_reputation(session, service, settings) -> None:
    await setup(session)
    await ReputationService(session, settings).change(
        CHAT_A, ADMIN_ID, USER_ID, 7, enforce_limits=False
    )

    assert await service.metric_value(CHAT_A, USER_ID) == 7


async def test_metric_messages(session, service, settings) -> None:
    await setup(session)
    await settings.set(CHAT_A, "ranks.metric", "messages", ADMIN_ID)
    members = MemberRepository(session)
    for _ in range(4):
        await members.increment_messages(CHAT_A, USER_ID)
    session.expire_all()
    member = await members.get(CHAT_A, USER_ID)

    assert await service.metric_value(CHAT_A, USER_ID, member) == 4


async def test_metric_sum(session, service, settings) -> None:
    await setup(session)
    await settings.set(CHAT_A, "ranks.metric", "sum", ADMIN_ID)
    await ReputationService(session, settings).change(
        CHAT_A, ADMIN_ID, USER_ID, 3, enforce_limits=False
    )
    members = MemberRepository(session)
    await members.increment_messages(CHAT_A, USER_ID)
    session.expire_all()
    member = await members.get(CHAT_A, USER_ID)

    assert await service.metric_value(CHAT_A, USER_ID, member) == 4


async def test_metric_is_per_chat(session, service, settings) -> None:
    await setup(session, CHAT_A)
    await setup(session, CHAT_B)
    await settings.set(CHAT_A, "ranks.metric", "messages", ADMIN_ID)

    assert await settings.get(CHAT_A, "ranks.metric") == "messages"
    assert await settings.get(CHAT_B, "ranks.metric") == "reputation"


# ─── Переходы ────────────────────────────────────────────────────────────────


async def test_rank_up_is_reported_once(session, service, settings) -> None:
    """Иначе бот поздравлял бы при каждом сообщении."""
    await setup(session)
    await make_ranks(service)
    reputation = ReputationService(session, settings)
    await reputation.change(CHAT_A, ADMIN_ID, USER_ID, 12, enforce_limits=False)

    first = await service.sync(CHAT_A, USER_ID)
    second = await service.sync(CHAT_A, USER_ID)

    assert first is not None
    assert first.direction == "up"
    assert first.new_name == "Свой"
    assert second is None


async def test_rank_down_is_detected(session, service, settings) -> None:
    await setup(session)
    await make_ranks(service)
    reputation = ReputationService(session, settings)
    await reputation.change(CHAT_A, ADMIN_ID, USER_ID, 60, enforce_limits=False)
    await service.sync(CHAT_A, USER_ID)

    await reputation.change(CHAT_A, ADMIN_ID, USER_ID, -55, enforce_limits=False)
    change = await service.sync(CHAT_A, USER_ID)

    assert change is not None
    assert change.direction == "down"
    assert change.old_name == "Ветеран"
    assert change.new_name == "Новичок"


async def test_no_ranks_means_no_changes(session, service) -> None:
    await setup(session)
    assert await service.sync(CHAT_A, USER_ID) is None


# ─── Настройка порогов влияет на рантайм ─────────────────────────────────────


async def test_threshold_change_takes_effect_immediately(
    session, cache, service, settings
) -> None:
    """Критическое требование ТЗ §12.

    Администратор меняет порог — и рантайм сразу считает по новому
    значению, а не по тому, что было при запуске.
    """
    await setup(session)
    await service.add(CHAT_A, "Ветеран", 100)
    await ReputationService(session, settings).change(
        CHAT_A, ADMIN_ID, USER_ID, 50, enforce_limits=False
    )

    assert await service.sync(CHAT_A, USER_ID) is None  # порог не достигнут

    # Порог снижен: ранг обязан появиться без перезапуска.
    await service.remove(CHAT_A, "Ветеран")
    await service.add(CHAT_A, "Ветеран", 40)

    change = await service.sync(CHAT_A, USER_ID)
    assert change is not None
    assert change.new_name == "Ветеран"


async def test_ranks_are_cached_and_invalidated(session, cache, service) -> None:
    await setup(session)
    await service.add(CHAT_A, "Новичок", 0)

    await service.ranks(CHAT_A)
    assert await cache.get(chat_key(ChatEntity.RANKS, CHAT_A)) is not None

    await service.add(CHAT_A, "Свой", 10)
    assert await cache.get(chat_key(ChatEntity.RANKS, CHAT_A)) is None


async def test_ranks_cache_is_per_chat(session, cache, service) -> None:
    await setup(session, CHAT_A)
    await setup(session, CHAT_B)
    await service.add(CHAT_A, "Новичок", 0)
    await service.add(CHAT_B, "Новичок", 0)

    await service.ranks(CHAT_A)
    await service.ranks(CHAT_B)
    await service.invalidate(CHAT_A)

    assert await cache.get(chat_key(ChatEntity.RANKS, CHAT_A)) is None
    assert await cache.get(chat_key(ChatEntity.RANKS, CHAT_B)) is not None


# ─── Ступени ─────────────────────────────────────────────────────────────────


async def test_duplicate_threshold_rejected(session, service) -> None:
    """Два ранга с одним порогом сделали бы результат неопределённым."""
    from sqlalchemy.exc import IntegrityError

    await setup(session)
    await service.add(CHAT_A, "Свой", 10)

    with pytest.raises(IntegrityError):
        await service.add(CHAT_A, "Другой", 10)


async def test_same_rank_name_allowed_in_another_chat(session, service) -> None:
    await setup(session, CHAT_A)
    await setup(session, CHAT_B)

    await service.add(CHAT_A, "Ветеран", 50)
    await service.add(CHAT_B, "Ветеран", 50)

    assert len(await service.ranks(CHAT_A)) == 1
    assert len(await service.ranks(CHAT_B)) == 1


async def test_remove_rank(session, service) -> None:
    await setup(session)
    await service.add(CHAT_A, "Свой", 10)

    assert await service.remove(CHAT_A, "Свой") is True
    assert await service.remove(CHAT_A, "Свой") is False


async def test_snapshot_shows_distance_to_next(session, service, settings) -> None:
    await setup(session)
    await make_ranks(service)
    await ReputationService(session, settings).change(
        CHAT_A, ADMIN_ID, USER_ID, 12, enforce_limits=False
    )

    snapshot = await service.snapshot(CHAT_A, USER_ID)

    assert snapshot.current.name == "Свой"
    assert snapshot.next_rank.name == "Ветеран"
    assert snapshot.to_next == 38
