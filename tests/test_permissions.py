"""Центральная проверка прав (ТЗ §4, §26, критерии §32.5, §32.6)."""

from __future__ import annotations

import pytest

from cache.keys import ChatEntity, chat_key
from cache.memory import MemoryCache
from core.constants import ANONYMOUS_ADMIN_BOT_ID, BotPermission, Role
from core.errors import BotMissingPermission, PermissionDenied
from mod_chats.repo import ChatRepository, MemberRepository
from permissions.service import PermissionService
from tests.test_chat_repository import make_chat, make_user

CHAT_A = -1001111111111
CHAT_B = -1002222222222
OWNER_ID = 8243233601
ADMIN_ID = 555
MEMBER_ID = 777
BOT_ID = 999


@pytest.fixture
def cache() -> MemoryCache:
    return MemoryCache()


@pytest.fixture
def permissions(session, cache) -> PermissionService:
    return PermissionService(session, cache, frozenset({OWNER_ID}), bot_id=BOT_ID)


async def _setup(session) -> None:
    await make_chat(session, CHAT_A, "Чат A")
    await make_chat(session, CHAT_B, "Чат B")
    for user_id in (OWNER_ID, ADMIN_ID, MEMBER_ID):
        await make_user(session, user_id)
    members = MemberRepository(session)
    await members.upsert(chat_id=CHAT_A, user_id=ADMIN_ID, role=Role.CHAT_ADMIN,
                         tg_status="administrator")
    await members.upsert(chat_id=CHAT_A, user_id=MEMBER_ID, role=Role.MEMBER, tg_status="member")
    # В чате B тот же администратор — обычный участник.
    await members.upsert(chat_id=CHAT_B, user_id=ADMIN_ID, role=Role.MEMBER, tg_status="member")


# ─── Роли ────────────────────────────────────────────────────────────────────


async def test_owner_is_owner_everywhere(session, permissions) -> None:
    """Владелец бота — единственная глобальная роль (ТЗ §4)."""
    await _setup(session)

    assert await permissions.role_of(CHAT_A, OWNER_ID) is Role.BOT_OWNER
    assert await permissions.role_of(CHAT_B, OWNER_ID) is Role.BOT_OWNER


async def test_role_depends_on_chat(session, permissions) -> None:
    """Администратор одного чата — рядовой участник другого (§32.5)."""
    await _setup(session)

    assert await permissions.role_of(CHAT_A, ADMIN_ID) is Role.CHAT_ADMIN
    assert await permissions.role_of(CHAT_B, ADMIN_ID) is Role.MEMBER


async def test_unknown_user_is_member(session, permissions) -> None:
    await _setup(session)
    assert await permissions.role_of(CHAT_A, 404404) is Role.MEMBER


async def test_anonymous_admin_is_treated_as_admin(session, permissions) -> None:
    """Telegram скрывает личность анонимного администратора.

    Писать анонимно может только администратор, поэтому такому отправителю
    выдаются права администратора — иначе владелец чата, включивший
    анонимность, не смог бы пользоваться командами.
    """
    await _setup(session)

    assert await permissions.role_of(CHAT_A, ANONYMOUS_ADMIN_BOT_ID) is Role.CHAT_ADMIN
    assert await permissions.role_of(CHAT_A, 12345, is_anonymous=True) is Role.CHAT_ADMIN


async def test_require_role_passes_and_fails(session, permissions) -> None:
    await _setup(session)

    assert await permissions.require_role(CHAT_A, ADMIN_ID, Role.MODERATOR) is Role.CHAT_ADMIN
    with pytest.raises(PermissionDenied):
        await permissions.require_role(CHAT_A, MEMBER_ID, Role.MODERATOR)


async def test_preloaded_member_is_used(session, permissions) -> None:
    """Middleware уже загрузила участника: повторный запрос не нужен."""
    await _setup(session)
    member = await MemberRepository(session).get(CHAT_A, ADMIN_ID)

    assert await permissions.role_of(CHAT_A, ADMIN_ID, member=member) is Role.CHAT_ADMIN


# ─── Права бота ──────────────────────────────────────────────────────────────


async def test_bot_permissions_read_from_chat(session, permissions) -> None:
    await _setup(session)
    assert await permissions.bot_can(CHAT_A, BotPermission.DELETE_MESSAGES) is True


async def test_missing_bot_permission_raises_with_name(session, permissions) -> None:
    """Пользователь должен узнать, какого права не хватает боту."""
    await _setup(session)

    with pytest.raises(BotMissingPermission) as info:
        await permissions.require_bot_permission(CHAT_A, BotPermission.RESTRICT_MEMBERS)

    assert info.value.permission == "can_restrict_members"
    assert info.value.text_key == "bot_no_permission"


async def test_bot_permissions_are_cached_per_chat(session, cache, permissions) -> None:
    await _setup(session)
    await permissions.bot_permissions(CHAT_A)

    assert await cache.get(chat_key(ChatEntity.BOT_PERMS, CHAT_A)) is not None
    assert await cache.get(chat_key(ChatEntity.BOT_PERMS, CHAT_B)) is None


async def test_permission_cache_invalidation_is_per_chat(session, cache, permissions) -> None:
    await _setup(session)
    await permissions.bot_permissions(CHAT_A)
    await permissions.bot_permissions(CHAT_B)

    await permissions.invalidate_bot_permissions(CHAT_A)

    assert await cache.get(chat_key(ChatEntity.BOT_PERMS, CHAT_A)) is None
    assert await cache.get(chat_key(ChatEntity.BOT_PERMS, CHAT_B)) is not None


async def test_permission_change_is_visible_after_invalidation(session, cache, permissions) -> None:
    """Права бота изменились — проверка обязана увидеть новое значение."""
    await _setup(session)
    assert await permissions.bot_can(CHAT_A, BotPermission.RESTRICT_MEMBERS) is False

    await ChatRepository(session).update_bot_permissions(
        CHAT_A, {"can_restrict_members": True}, "administrator"
    )
    await permissions.invalidate_bot_permissions(CHAT_A)

    assert await permissions.bot_can(CHAT_A, BotPermission.RESTRICT_MEMBERS) is True


# ─── Защита цели ─────────────────────────────────────────────────────────────


async def test_admin_can_act_on_member(session, permissions) -> None:
    await _setup(session)
    assert await permissions.can_act_on(CHAT_A, ADMIN_ID, MEMBER_ID) is True


async def test_admin_cannot_act_on_equal(session, permissions) -> None:
    """Иначе два администратора способны заблокировать друг друга."""
    await _setup(session)
    await MemberRepository(session).upsert(
        chat_id=CHAT_A, user_id=MEMBER_ID, role=Role.CHAT_ADMIN, tg_status="administrator"
    )

    assert await permissions.can_act_on(CHAT_A, ADMIN_ID, MEMBER_ID) is False


async def test_nobody_can_act_on_bot_owner(session, permissions) -> None:
    await _setup(session)
    assert await permissions.can_act_on(CHAT_A, ADMIN_ID, OWNER_ID) is False


async def test_bot_cannot_be_targeted(session, permissions) -> None:
    await _setup(session)
    assert await permissions.can_act_on(CHAT_A, ADMIN_ID, BOT_ID) is False


async def test_self_action_is_blocked(session, permissions) -> None:
    await _setup(session)
    assert await permissions.can_act_on(CHAT_A, ADMIN_ID, ADMIN_ID) is False


async def test_require_can_act_on_raises(session, permissions) -> None:
    await _setup(session)
    with pytest.raises(PermissionDenied):
        await permissions.require_can_act_on(CHAT_A, ADMIN_ID, OWNER_ID)


async def test_rights_in_one_chat_do_not_grant_rights_in_another(session, permissions) -> None:
    """Критерий приёмки §32.6: проверка всегда учитывает chat_id."""
    await _setup(session)

    assert await permissions.can_act_on(CHAT_A, ADMIN_ID, MEMBER_ID) is True
    assert await permissions.can_act_on(CHAT_B, ADMIN_ID, MEMBER_ID) is False
