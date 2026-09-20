"""Изоляция данных между чатами (ТЗ §22, критерии приёмки §32.5 и §32.8).

Ключевая проверка проекта: один процесс обслуживает много чатов, и данные
одного чата не могут повлиять на другой.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from core.constants import Role
from mod_chats.repo import ChatRepository, MemberRepository, UserRepository
from tests.conftest import TEST_DATABASE_URL

CHAT_A = -1001111111111
CHAT_B = -1002222222222
USER = 8243233601


async def _prepare(session: AsyncSession) -> None:
    chats = ChatRepository(session)
    for chat_id, title in ((CHAT_A, "Чат A"), (CHAT_B, "Чат B")):
        await chats.upsert(
            chat_id=chat_id,
            type_="supergroup",
            title=title,
            username=None,
            bot_status="administrator",
            bot_permissions={},
        )
    await UserRepository(session).upsert(
        user_id=USER, username="tester", first_name="Тест", last_name=None
    )


async def test_same_user_has_independent_roles_in_two_chats(session: AsyncSession) -> None:
    """Администратор чата A остаётся рядовым участником чата B (§32.5)."""
    await _prepare(session)
    members = MemberRepository(session)

    await members.upsert(chat_id=CHAT_A, user_id=USER, role=Role.CHAT_ADMIN,
                         tg_status="administrator")
    await members.upsert(chat_id=CHAT_B, user_id=USER, role=Role.MEMBER, tg_status="member")
    session.expire_all()

    in_a = await members.get(CHAT_A, USER)
    in_b = await members.get(CHAT_B, USER)

    assert in_a is not None and in_a.role == Role.CHAT_ADMIN
    assert in_b is not None and in_b.role == Role.MEMBER
    assert in_a.is_staff and not in_b.is_staff


async def test_promotion_in_one_chat_does_not_leak(session: AsyncSession) -> None:
    await _prepare(session)
    members = MemberRepository(session)
    await members.upsert(chat_id=CHAT_A, user_id=USER, role=Role.MEMBER, tg_status="member")
    await members.upsert(chat_id=CHAT_B, user_id=USER, role=Role.MEMBER, tg_status="member")

    await members.upsert(chat_id=CHAT_A, user_id=USER, role=Role.CHAT_OWNER, tg_status="creator")
    session.expire_all()

    in_b = await members.get(CHAT_B, USER)
    assert in_b is not None
    assert in_b.role == Role.MEMBER


async def test_activity_counters_are_per_chat(session: AsyncSession) -> None:
    await _prepare(session)
    members = MemberRepository(session)
    await members.ensure_exists(CHAT_A, USER)
    await members.ensure_exists(CHAT_B, USER)

    for _ in range(3):
        await members.increment_messages(CHAT_A, USER)
    await members.increment_messages(CHAT_B, USER)
    session.expire_all()

    in_a = await members.get(CHAT_A, USER)
    in_b = await members.get(CHAT_B, USER)
    assert in_a is not None and in_a.messages_total == 3
    assert in_b is not None and in_b.messages_total == 1


async def test_admin_list_of_one_chat_never_includes_another(session: AsyncSession) -> None:
    await _prepare(session)
    members = MemberRepository(session)
    await members.upsert(chat_id=CHAT_A, user_id=USER, role=Role.CHAT_ADMIN,
                         tg_status="administrator")
    await members.upsert(chat_id=CHAT_B, user_id=USER, role=Role.MEMBER, tg_status="member")

    staff_a = await members.list_staff(CHAT_A)
    staff_b = await members.list_staff(CHAT_B)

    assert [m.user_id for m in staff_a] == [USER]
    assert staff_b == []


async def test_admin_sees_only_chats_where_he_has_rights(session: AsyncSession) -> None:
    """Администратор чата A не должен видеть чат B в выборе (§32.3)."""
    await _prepare(session)
    members = MemberRepository(session)
    await members.upsert(chat_id=CHAT_A, user_id=USER, role=Role.CHAT_ADMIN,
                         tg_status="administrator")
    await members.upsert(chat_id=CHAT_B, user_id=USER, role=Role.MEMBER, tg_status="member")

    visible = await members.list_chats_for_user(USER)

    assert [c.chat_id for c in visible] == [CHAT_A]


async def test_data_survives_restart_and_stays_separate(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Обязательный сценарий ТЗ §31: значения переживают перезапуск.

    Изменяем данные чата A, убеждаемся, что чат B не затронут, затем
    полностью пересоздаём подключение к базе — как при перезапуске
    приложения — и проверяем оба чата заново.
    """
    async with session_factory() as setup:
        await _prepare(setup)
        members = MemberRepository(setup)
        await members.upsert(chat_id=CHAT_A, user_id=USER, role=Role.CHAT_ADMIN,
                             tg_status="administrator")
        await members.upsert(chat_id=CHAT_B, user_id=USER, role=Role.MEMBER, tg_status="member")
        await setup.commit()

    # Перезапуск приложения: прежний пул закрыт, создаётся новое подключение.
    fresh_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    fresh_factory = async_sessionmaker(bind=fresh_engine, class_=AsyncSession)
    try:
        async with fresh_factory() as after_restart:
            members = MemberRepository(after_restart)
            in_a = await members.get(CHAT_A, USER)
            in_b = await members.get(CHAT_B, USER)

            assert in_a is not None and in_a.role == Role.CHAT_ADMIN
            assert in_b is not None and in_b.role == Role.MEMBER
    finally:
        await fresh_engine.dispose()
