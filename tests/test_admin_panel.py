"""Админ-панель: доступ, динамическое меню, редактирование (ТЗ §3, §16)."""

from __future__ import annotations

import pytest
from aiogram.enums import ButtonStyle
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from cache.memory import MemoryCache
from core.constants import Role
from core.errors import PermissionDenied
from core.registry import build_registry as build_modules
from mod_admin import menu
from mod_admin.handlers import _require_access
from mod_chats.repo import MemberRepository
from mod_moderation.spec import SETTINGS as MODERATION_SETTINGS
from permissions.service import PermissionService
from settings.defs import CORE_SETTINGS, SettingsRegistry
from settings.defs import build_registry as build_settings
from settings.service import SettingsService
from texts.defs import CORE_TEXTS, TextRegistry
from texts.defs import build_registry as build_texts
from texts.entities import EntityText
from texts.service import TextService
from tests.test_chat_repository import make_chat, make_user

CHAT_A = -1001111111111
CHAT_B = -1002222222222
ADMIN_ID = 8243233601
STRANGER_ID = 404
OWNER_ID = 1


def specs() -> list:
    from mod_admin.spec import MODULE as admin
    from mod_chats.spec import MODULE as chats
    from mod_moderation.spec import MODULE as moderation

    return [chats, admin, moderation]


@pytest.fixture
def cache() -> MemoryCache:
    return MemoryCache()


@pytest.fixture
def texts(session, cache) -> TextService:
    return TextService(session, cache, build_texts(specs()))


@pytest.fixture
def settings(session, cache) -> SettingsService:
    return SettingsService(session, cache, build_settings(specs()))


@pytest.fixture
def permissions(session, cache) -> PermissionService:
    return PermissionService(session, cache, frozenset({OWNER_ID}), bot_id=999)


async def setup(session) -> None:
    await make_chat(session, CHAT_A, "Чат A")
    await make_chat(session, CHAT_B, "Чат B")
    for user_id in (ADMIN_ID, STRANGER_ID, OWNER_ID):
        await make_user(session, user_id)
    members = MemberRepository(session)
    await members.upsert(chat_id=CHAT_A, user_id=ADMIN_ID, role=Role.CHAT_ADMIN,
                         tg_status="administrator")
    await members.upsert(chat_id=CHAT_B, user_id=ADMIN_ID, role=Role.MEMBER, tg_status="member")


def make_state(user_id: int) -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=999, chat_id=user_id, user_id=user_id),
    )


# ─── Доступ ──────────────────────────────────────────────────────────────────


async def test_admin_sees_only_his_chats(session) -> None:
    """Критерий приёмки §32.3: чужие чаты в панели не появляются."""
    await setup(session)

    chats = await MemberRepository(session).list_chats_for_user(ADMIN_ID, Role.CHAT_ADMIN)

    assert [chat.chat_id for chat in chats] == [CHAT_A]


async def test_stranger_sees_nothing(session) -> None:
    await setup(session)

    chats = await MemberRepository(session).list_chats_for_user(STRANGER_ID, Role.CHAT_ADMIN)

    assert chats == []


async def test_access_is_rechecked_on_every_action(session, permissions) -> None:
    """Нажать кнопку может и тот, у кого права уже отобрали (ТЗ §16)."""
    await setup(session)
    state = make_state(ADMIN_ID)
    await state.update_data(chat_id=CHAT_A)

    assert await _require_access(state, permissions, ADMIN_ID) == CHAT_A

    # Администратора понизили, пока панель была открыта.
    await MemberRepository(session).upsert(
        chat_id=CHAT_A, user_id=ADMIN_ID, role=Role.MEMBER, tg_status="member"
    )
    with pytest.raises(PermissionDenied):
        await _require_access(state, permissions, ADMIN_ID)


async def test_access_to_foreign_chat_is_refused(session, permissions) -> None:
    """Подмена чата в состоянии не даёт доступа к чужим настройкам."""
    await setup(session)
    state = make_state(ADMIN_ID)
    await state.update_data(chat_id=CHAT_B)

    with pytest.raises(PermissionDenied):
        await _require_access(state, permissions, ADMIN_ID)


async def test_no_chat_selected_is_refused(session, permissions) -> None:
    await setup(session)

    with pytest.raises(PermissionDenied):
        await _require_access(make_state(ADMIN_ID), permissions, ADMIN_ID)


# ─── Экраны ──────────────────────────────────────────────────────────────────


async def test_chat_list_shows_titles(session, texts) -> None:
    await setup(session)
    chats = await MemberRepository(session).list_chats_for_user(ADMIN_ID, Role.CHAT_ADMIN)

    screen = await menu.chat_list_screen(texts, chats)

    assert screen.text_key == "admin_select_chat"
    assert screen.rows[0][0].text == "Чат A"


async def test_empty_chat_list_has_no_buttons(texts) -> None:
    screen = await menu.chat_list_screen(texts, [])

    assert screen.text_key == "admin_no_chats"
    assert screen.rows == []


async def test_root_menu_labels_come_from_texts(session, texts) -> None:
    """Подписи кнопок настраиваемы, а не зашиты в код."""
    await setup(session)
    await texts.set_global("admin_btn_settings", EntityText(text="Параметры"), OWNER_ID)

    screen = await menu.root_screen(texts, CHAT_A, "Чат A")

    labels = [button.text for row in screen.rows for button in row]
    assert "Параметры" in labels


async def test_module_screen_marks_state_with_colour(session, texts, settings) -> None:
    """Включённый модуль — зелёная кнопка, выключенный — красная."""
    await setup(session)
    registry = build_modules(specs())

    screen = await menu.modules_screen(texts, settings, registry, CHAT_A)
    enabled_styles = [button.style for row in screen.rows[:-1] for button in row]
    assert all(style is ButtonStyle.SUCCESS for style in enabled_styles)

    await settings.set(CHAT_A, "modules.moderation.enabled", False, ADMIN_ID)
    screen = await menu.modules_screen(texts, settings, registry, CHAT_A)
    styles = {button.text: button.style for row in screen.rows[:-1] for button in row}
    assert any(style is ButtonStyle.DANGER for style in styles.values())


async def test_module_settings_screen_shows_values(session, texts, settings) -> None:
    await setup(session)
    registry = build_settings(specs())

    screen = await menu.module_settings_screen(texts, settings, registry, CHAT_A, "moderation")

    labels = [button.text for row in screen.rows[:-1] for button in row]
    assert any("3" in label for label in labels)  # порог предупреждений


async def test_setting_screen_offers_toggle_for_boolean(session, texts) -> None:
    await setup(session)
    registry = SettingsRegistry([*CORE_SETTINGS, *MODERATION_SETTINGS])
    definition = registry.get("core.staff_immune")

    screen = await menu.setting_screen(texts, CHAT_A, definition, True)

    assert screen.rows[0][0].callback_data.endswith("toggle")


async def test_setting_screen_offers_input_for_number(session, texts) -> None:
    await setup(session)
    registry = SettingsRegistry([*CORE_SETTINGS, *MODERATION_SETTINGS])
    definition = registry.get("moderation.warn_limit")

    screen = await menu.setting_screen(texts, CHAT_A, definition, 3)

    assert screen.rows[0][0].callback_data.endswith("edit")


async def test_texts_screen_marks_overridden(session, texts) -> None:
    """Изменённый текст отмечается, чтобы было видно, что настроено."""
    await setup(session)
    registry = TextRegistry(list(CORE_TEXTS))
    await texts.set_for_chat(CHAT_A, "permission_denied", EntityText(text="Нельзя"), ADMIN_ID)

    screen = await menu.module_texts_screen(texts, registry, CHAT_A, "core")

    marked = [button.text for row in screen.rows[:-1] for button in row if "✎" in button.text]
    assert len(marked) == 1


async def test_pagination_splits_long_lists(texts) -> None:
    class FakeChat:
        def __init__(self, index: int) -> None:
            self.chat_id = -1000 - index
            self.title = f"Чат {index}"

    screen = await menu.chat_list_screen(texts, [FakeChat(i) for i in range(20)])

    # Восемь чатов и строка перелистывания.
    assert len(screen.rows) == menu.PAGE_SIZE + 1


# ─── Изоляция ────────────────────────────────────────────────────────────────


async def test_panel_changes_affect_only_selected_chat(session, settings) -> None:
    await setup(session)

    await settings.set(CHAT_A, "moderation.warn_limit", 5, ADMIN_ID)

    assert await settings.get(CHAT_A, "moderation.warn_limit") == 5
    assert await settings.get(CHAT_B, "moderation.warn_limit") == 3
