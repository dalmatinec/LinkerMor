"""Статистика чата и рассылка по администраторам."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.constants import ChatStatus, Role
from mod_chats.repo import ChatRepository, MemberRepository
from mod_stats.models import DailyActivity
from mod_stats.repo import StatsRepository
from mod_stats.service import StatsService, sparkline
from tests.test_chat_repository import make_chat, make_user

CHAT_A = -1001111111111
CHAT_B = -1002222222222
ADMIN_ID = 8243233601
USER_ID = 555
OTHER_ID = 777


@pytest.fixture
def repo(session) -> StatsRepository:
    return StatsRepository(session)


async def setup(session, chat_id: int = CHAT_A) -> None:
    await make_chat(session, chat_id)
    for user_id in (ADMIN_ID, USER_ID, OTHER_ID):
        await make_user(session, user_id)


# ─── График ──────────────────────────────────────────────────────────────────


def test_sparkline_scales_to_peak() -> None:
    """Строка отображается одинаково везде и не требует загрузки картинки."""
    assert sparkline([0, 4, 8]) == "▁▄█"


def test_sparkline_of_silence() -> None:
    assert sparkline([0, 0, 0]) == "▁▁▁"


def test_sparkline_of_nothing() -> None:
    assert sparkline([]) == ""


# ─── Сбор ────────────────────────────────────────────────────────────────────


async def test_messages_are_counted_per_day(session, repo) -> None:
    await setup(session)

    for _ in range(3):
        await repo.register_message(CHAT_A, USER_ID)

    today = datetime.now(UTC).date()
    assert await repo.messages_since(CHAT_A, today) == 3


async def test_counting_is_isolated_between_chats(session, repo) -> None:
    await setup(session, CHAT_A)
    await setup(session, CHAT_B)

    await repo.register_message(CHAT_A, USER_ID)

    today = datetime.now(UTC).date()
    assert await repo.messages_since(CHAT_A, today) == 1
    assert await repo.messages_since(CHAT_B, today) == 0


async def test_active_members_are_distinct(session, repo) -> None:
    await setup(session)
    for _ in range(5):
        await repo.register_message(CHAT_A, USER_ID)
    await repo.register_message(CHAT_A, OTHER_ID)

    today = datetime.now(UTC).date()
    assert await repo.messages_since(CHAT_A, today) == 6
    assert await repo.active_members_since(CHAT_A, today) == 2


async def test_top_members_ordered(session, repo) -> None:
    await setup(session)
    for _ in range(4):
        await repo.register_message(CHAT_A, USER_ID)
    await repo.register_message(CHAT_A, OTHER_ID)

    top = await repo.top_members(CHAT_A, datetime.now(UTC).date())

    assert top == [(USER_ID, 4), (OTHER_ID, 1)]


async def test_old_days_are_outside_the_window(session, repo) -> None:
    await setup(session)
    old = datetime.now(UTC).date() - timedelta(days=40)
    session.add(DailyActivity(chat_id=CHAT_A, user_id=USER_ID, day=old, messages=100))
    await session.flush()

    week = datetime.now(UTC).date() - timedelta(days=6)
    assert await repo.messages_since(CHAT_A, week) == 0


async def test_daily_series_fills_silent_days(session, repo) -> None:
    """В графике должны быть все дни, иначе картина искажается."""
    await setup(session)
    await repo.register_message(CHAT_A, USER_ID)

    series = await repo.daily_series(CHAT_A, days=7)

    assert len(series) == 7
    assert series[-1][1] == 1
    assert sum(count for _, count in series[:-1]) == 0


# ─── Сводка ──────────────────────────────────────────────────────────────────


async def test_report_collects_numbers(session) -> None:
    await setup(session)
    members = MemberRepository(session)
    await members.upsert(chat_id=CHAT_A, user_id=ADMIN_ID, role=Role.CHAT_ADMIN,
                         tg_status="administrator")
    await members.ensure_exists(CHAT_A, USER_ID)

    service = StatsService(session)
    for _ in range(3):
        await service.register_message(CHAT_A, USER_ID)

    stats = await service.collect(CHAT_A, "Чат A")

    assert stats.values["messages_today"] == "3"
    assert stats.values["active_today"] == "1"
    assert stats.values["staff_total"] == "1"
    assert stats.values["chat_title"] == "Чат A"
    assert len(stats.values["chart"]) == 7


async def test_report_lists_top_members_by_name(session) -> None:
    await setup(session)
    service = StatsService(session)
    await service.register_message(CHAT_A, USER_ID)

    stats = await service.collect(CHAT_A, "Чат A")

    assert "1." in stats.values["items"]


async def test_report_template_uses_only_known_placeholders() -> None:
    """Иначе в сводке останутся пустые места."""
    from mod_stats.spec import TEXTS
    from texts.entities import EntityText
    from texts.placeholders import unknown_placeholders

    template = EntityText(text=TEXTS[0].default)
    assert unknown_placeholders(template) == set()


# ─── Рассылка ────────────────────────────────────────────────────────────────


async def test_broadcast_recipients_are_admins_without_duplicates(session) -> None:
    """Администратор двух чатов должен получить сообщение один раз."""
    await setup(session, CHAT_A)
    await setup(session, CHAT_B)
    members = MemberRepository(session)
    for chat_id in (CHAT_A, CHAT_B):
        await members.upsert(chat_id=chat_id, user_id=ADMIN_ID, role=Role.CHAT_ADMIN,
                             tg_status="administrator")
    await members.upsert(chat_id=CHAT_A, user_id=USER_ID, role=Role.MEMBER,
                         tg_status="member")

    recipients = await members.all_admin_user_ids()

    assert recipients == [ADMIN_ID]


async def test_broadcast_skips_inactive_chats(session) -> None:
    """Из отключённого чата администраторы рассылку получать не должны."""
    await setup(session, CHAT_A)
    members = MemberRepository(session)
    await members.upsert(chat_id=CHAT_A, user_id=ADMIN_ID, role=Role.CHAT_ADMIN,
                         tg_status="administrator")

    await ChatRepository(session).set_status(CHAT_A, ChatStatus.INACTIVE, "kicked")

    assert await members.all_admin_user_ids() == []
