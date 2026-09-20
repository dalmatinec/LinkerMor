"""Репозитории чатов на настоящей базе."""

from __future__ import annotations

from core.constants import ChatStatus, Role
from mod_chats.repo import ChatRepository, MemberRepository, UserRepository

CHAT_A = -1001111111111
CHAT_B = -1002222222222
USER = 8243233601


async def make_chat(session, chat_id: int, title: str = "Чат") -> None:
    await ChatRepository(session).upsert(
        chat_id=chat_id,
        type_="supergroup",
        title=title,
        username=None,
        bot_status="administrator",
        bot_permissions={"can_delete_messages": True},
        added_by_user_id=USER,
    )


async def make_user(session, user_id: int, username: str | None = None) -> None:
    await UserRepository(session).upsert(
        user_id=user_id, username=username, first_name="Тест", last_name=None
    )


async def test_upsert_creates_then_updates(session) -> None:
    repo = ChatRepository(session)
    await make_chat(session, CHAT_A, "Старое название")
    await make_chat(session, CHAT_A, "Новое название")

    chat = await repo.get(CHAT_A)
    assert chat is not None
    assert chat.title == "Новое название"
    assert chat.status == ChatStatus.ACTIVE


async def test_reconnect_keeps_original_connection_data(session) -> None:
    """Возвращение бота не должно стирать историю подключения."""
    repo = ChatRepository(session)
    await make_chat(session, CHAT_A)
    first = await repo.get(CHAT_A)
    assert first is not None
    connected_at, added_by = first.connected_at, first.added_by_user_id

    await repo.set_status(CHAT_A, ChatStatus.INACTIVE, "kicked")
    await session.flush()
    session.expire_all()

    await repo.upsert(
        chat_id=CHAT_A,
        type_="supergroup",
        title="Чат",
        username=None,
        bot_status="administrator",
        bot_permissions={},
        added_by_user_id=999,  # бота вернул другой человек
    )
    session.expire_all()

    restored = await repo.get(CHAT_A)
    assert restored is not None
    assert restored.status == ChatStatus.ACTIVE
    assert restored.connected_at == connected_at
    assert restored.added_by_user_id == added_by


async def test_migration_marks_old_chat_and_moves_members(session) -> None:
    """Переезд в супергруппу сохраняет участников под новым chat_id."""
    new_chat_id = -1009999999999
    await make_chat(session, CHAT_A)
    await make_user(session, USER)
    await MemberRepository(session).upsert(
        chat_id=CHAT_A, user_id=USER, role=Role.CHAT_ADMIN, tg_status="administrator"
    )

    await make_chat(session, new_chat_id, "Супергруппа")
    moved = await MemberRepository(session).move_to_chat(CHAT_A, new_chat_id)
    await ChatRepository(session).mark_migrated(CHAT_A, new_chat_id)
    session.expire_all()

    old = await ChatRepository(session).get(CHAT_A)
    assert old is not None
    assert old.status == ChatStatus.MIGRATED
    assert old.migrated_to_chat_id == new_chat_id
    assert moved == 1
    assert await MemberRepository(session).get(new_chat_id, USER) is not None


async def test_username_lookup_is_case_insensitive(session) -> None:
    await make_user(session, USER, username="Durov")
    repo = UserRepository(session)

    assert (await repo.find_by_username("durov")) is not None
    assert (await repo.find_by_username("@DUROV")) is not None
    assert (await repo.find_by_username("unknown")) is None


async def test_message_counter_is_atomic(session) -> None:
    """Счётчик рангов увеличивается запросом, без чтения предыдущего значения."""
    await make_chat(session, CHAT_A)
    await make_user(session, USER)
    members = MemberRepository(session)
    await members.ensure_exists(CHAT_A, USER)

    for expected in (1, 2, 3):
        assert await members.increment_messages(CHAT_A, USER) == expected


async def test_ensure_exists_does_not_reset_role(session) -> None:
    await make_chat(session, CHAT_A)
    await make_user(session, USER)
    members = MemberRepository(session)
    await members.upsert(chat_id=CHAT_A, user_id=USER, role=Role.CHAT_ADMIN,
                         tg_status="administrator")

    await members.ensure_exists(CHAT_A, USER)
    session.expire_all()

    member = await members.get(CHAT_A, USER)
    assert member is not None
    assert member.role == Role.CHAT_ADMIN


async def test_demote_missing_admins(session) -> None:
    """Пока бот был офлайн, администратора могли снять."""
    await make_chat(session, CHAT_A)
    await make_user(session, USER)
    await make_user(session, 555, "second")
    members = MemberRepository(session)
    await members.upsert(chat_id=CHAT_A, user_id=USER, role=Role.CHAT_ADMIN,
                         tg_status="administrator")
    await members.upsert(chat_id=CHAT_A, user_id=555, role=Role.CHAT_ADMIN,
                         tg_status="administrator")

    demoted = await members.demote_missing_admins(CHAT_A, keep_user_ids={USER})
    session.expire_all()

    assert demoted == 1
    still_admin = await members.get(CHAT_A, USER)
    removed = await members.get(CHAT_A, 555)
    assert still_admin is not None and still_admin.role == Role.CHAT_ADMIN
    assert removed is not None and removed.role == Role.MEMBER
