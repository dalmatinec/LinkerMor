"""Подключение и отключение чата (ТЗ §5)."""

from __future__ import annotations

from datetime import UTC, datetime

from aiogram.types import Chat as TgChat
from aiogram.types import (
    ChatMemberAdministrator,
    ChatMemberLeft,
    ChatMemberMember,
    ChatMemberOwner,
    ChatMemberUpdated,
)
from aiogram.types import User as TgUser

from core.constants import ChatStatus, Role
from mod_chats.lifecycle import ChatLifecycleService, extract_permissions, role_from_status
from mod_chats.repo import ChatRepository, MemberRepository

CHAT_ID = -1001111111111
ACTOR_ID = 8243233601
BOT_ID = 777

TG_CHAT = TgChat(id=CHAT_ID, type="supergroup", title="Тестовый чат")
ACTOR = TgUser(id=ACTOR_ID, is_bot=False, first_name="Владелец", username="owner")
BOT_USER = TgUser(id=BOT_ID, is_bot=True, first_name="LinkerMor", username="linkermor_bot")


def admin_member(user: TgUser, *, can_restrict: bool = True) -> ChatMemberAdministrator:
    return ChatMemberAdministrator(
        user=user,
        can_be_edited=False,
        is_anonymous=False,
        can_manage_chat=True,
        can_delete_messages=True,
        can_manage_video_chats=True,
        can_restrict_members=can_restrict,
        can_promote_members=False,
        can_change_info=True,
        can_invite_users=True,
        can_post_stories=False,
        can_edit_stories=False,
        can_delete_stories=False,
        can_send_welcome_messages=True,
    )


def bot_update(old, new) -> ChatMemberUpdated:  # noqa: ANN001
    return ChatMemberUpdated(
        chat=TG_CHAT,
        from_user=ACTOR,
        date=datetime.now(UTC),
        old_chat_member=old,
        new_chat_member=new,
    )


async def test_bot_added_connects_chat(session) -> None:
    event = bot_update(ChatMemberLeft(user=BOT_USER), admin_member(BOT_USER))

    chat = await ChatLifecycleService(session).handle_bot_update(event)

    assert chat is not None
    assert chat.chat_id == CHAT_ID
    assert chat.status == ChatStatus.ACTIVE
    assert chat.bot_status == "administrator"
    assert chat.bot_permissions["can_restrict_members"] is True
    assert chat.added_by_user_id == ACTOR_ID


async def test_person_who_added_bot_becomes_admin(session) -> None:
    """Иначе тот, кто подключил бота, не смог бы открыть его настройки."""
    await ChatLifecycleService(session).handle_bot_update(
        bot_update(ChatMemberLeft(user=BOT_USER), admin_member(BOT_USER))
    )

    member = await MemberRepository(session).get(CHAT_ID, ACTOR_ID)
    assert member is not None
    assert member.role == Role.CHAT_ADMIN


async def test_bot_removed_deactivates_chat_but_keeps_data(session) -> None:
    """Данные чата переживают исключение бота (ТЗ §5)."""
    service = ChatLifecycleService(session)
    await service.handle_bot_update(bot_update(ChatMemberLeft(user=BOT_USER), admin_member(BOT_USER)))

    result = await service.handle_bot_update(
        bot_update(admin_member(BOT_USER), ChatMemberLeft(user=BOT_USER))
    )
    session.expire_all()

    assert result is None
    chat = await ChatRepository(session).get(CHAT_ID)
    assert chat is not None
    assert chat.status == ChatStatus.INACTIVE
    assert chat.bot_status == "left"
    # Запись о том, кто подключил чат, не потеряна.
    assert chat.added_by_user_id == ACTOR_ID


async def test_permission_loss_is_recorded(session) -> None:
    """Снятие права у бота должно быть видно до попытки действия."""
    service = ChatLifecycleService(session)
    await service.handle_bot_update(
        bot_update(ChatMemberLeft(user=BOT_USER), admin_member(BOT_USER, can_restrict=True))
    )

    await service.handle_bot_update(
        bot_update(
            admin_member(BOT_USER, can_restrict=True),
            admin_member(BOT_USER, can_restrict=False),
        )
    )
    session.expire_all()

    chat = await ChatRepository(session).get(CHAT_ID)
    assert chat is not None
    assert chat.bot_permissions["can_restrict_members"] is False


async def test_member_promotion_updates_role(session) -> None:
    service = ChatLifecycleService(session)
    await service.handle_bot_update(bot_update(ChatMemberLeft(user=BOT_USER), admin_member(BOT_USER)))

    target = TgUser(id=555, is_bot=False, first_name="Участник", username="member")
    await service.handle_member_update(
        ChatMemberUpdated(
            chat=TG_CHAT,
            from_user=ACTOR,
            date=datetime.now(UTC),
            old_chat_member=ChatMemberMember(user=target),
            new_chat_member=admin_member(target),
        )
    )

    member = await MemberRepository(session).get(CHAT_ID, 555)
    assert member is not None
    assert member.role == Role.CHAT_ADMIN
    assert member.tg_permissions["can_delete_messages"] is True


async def test_role_mapping() -> None:
    assert role_from_status("creator") is Role.CHAT_OWNER
    assert role_from_status("administrator") is Role.CHAT_ADMIN
    assert role_from_status("member") is Role.MEMBER
    assert role_from_status("restricted") is Role.MEMBER


async def test_ordinary_member_has_no_admin_permissions() -> None:
    """У обычного участника словарь прав пуст, а не заполнен False."""
    assert extract_permissions(ChatMemberMember(user=ACTOR)) == {}


async def test_owner_permissions_extracted() -> None:
    owner = ChatMemberOwner(user=ACTOR, is_anonymous=True, custom_title="Босс")
    assert extract_permissions(owner) == {}
    assert role_from_status(owner.status) is Role.CHAT_OWNER
