"""Сервис настроек: значение по умолчанию, проверка, кеш, журнал (ТЗ §23)."""

from __future__ import annotations

import pytest

from cache.keys import ChatEntity, chat_key
from cache.memory import MemoryCache
from core.errors import SettingValidationError
from settings.defs import CORE_SETTINGS, SettingDef, SettingsRegistry, build_registry
from settings.service import SettingsService
from tests.test_chat_repository import make_chat

CHAT_A = -1001111111111
ACTOR = 8243233601


@pytest.fixture
def registry() -> SettingsRegistry:
    return SettingsRegistry(list(CORE_SETTINGS))


@pytest.fixture
def cache() -> MemoryCache:
    return MemoryCache()


@pytest.fixture
def service(session, cache, registry) -> SettingsService:
    return SettingsService(session, cache, registry)


async def test_unset_setting_returns_default(session, service) -> None:
    await make_chat(session, CHAT_A)
    assert await service.get(CHAT_A, "core.staff_immune") is True


async def test_set_then_get(session, service) -> None:
    await make_chat(session, CHAT_A)

    await service.set(CHAT_A, "core.staff_immune", False, ACTOR)

    assert await service.get(CHAT_A, "core.staff_immune") is False


async def test_change_is_visible_immediately(session, service, cache) -> None:
    """Кеш обязан сброситься при записи, иначе настройка «не работает»."""
    await make_chat(session, CHAT_A)
    await service.get(CHAT_A, "core.staff_immune")  # наполняем кеш
    assert await cache.get(chat_key(ChatEntity.SETTINGS, CHAT_A)) is not None

    await service.set(CHAT_A, "core.staff_immune", False, ACTOR)

    assert await cache.get(chat_key(ChatEntity.SETTINGS, CHAT_A)) is None
    assert await service.get(CHAT_A, "core.staff_immune") is False


async def test_reset_returns_to_default(session, service) -> None:
    await make_chat(session, CHAT_A)
    await service.set(CHAT_A, "core.staff_immune", False, ACTOR)

    await service.reset(CHAT_A, "core.staff_immune", ACTOR)

    assert await service.get(CHAT_A, "core.staff_immune") is True


async def test_changes_are_recorded_in_audit(session, service) -> None:
    await make_chat(session, CHAT_A)
    await service.set(CHAT_A, "core.staff_immune", False, ACTOR)

    history = await service.history(CHAT_A)

    assert len(history) == 1
    assert history[0].key == "core.staff_immune"
    assert history[0].old_value is True
    assert history[0].new_value is False
    assert history[0].actor_id == ACTOR


async def test_unknown_setting_is_rejected(service) -> None:
    with pytest.raises(SettingValidationError):
        await service.get(CHAT_A, "выдуманная.настройка")


@pytest.mark.parametrize("value", ["не-число", 3.5, None])
async def test_invalid_number_rejected(session, cache, value) -> None:
    await make_chat(session, CHAT_A)
    registry = SettingsRegistry(
        [SettingDef("test.limit", 3, int, "test", "Порог", minimum=1, maximum=10)]
    )
    service = SettingsService(session, cache, registry)

    with pytest.raises(SettingValidationError):
        await service.set(CHAT_A, "test.limit", value, ACTOR)


@pytest.mark.parametrize("value", [0, 11])
async def test_number_out_of_bounds_rejected(session, cache, value) -> None:
    await make_chat(session, CHAT_A)
    registry = SettingsRegistry(
        [SettingDef("test.limit", 3, int, "test", "Порог", minimum=1, maximum=10)]
    )
    service = SettingsService(session, cache, registry)

    with pytest.raises(SettingValidationError):
        await service.set(CHAT_A, "test.limit", value, ACTOR)


async def test_choice_setting_rejects_unknown_option(session, service) -> None:
    await make_chat(session, CHAT_A)
    with pytest.raises(SettingValidationError):
        await service.set(CHAT_A, "core.language", "кз", ACTOR)


async def test_boolean_accepts_human_input(session, service) -> None:
    """Значение приходит из кнопки или текста: обе формы должны работать."""
    await make_chat(session, CHAT_A)

    assert await service.set(CHAT_A, "core.delete_commands", "да", ACTOR) is True
    assert await service.set(CHAT_A, "core.delete_commands", "false", ACTOR) is False


async def test_duplicate_setting_definition_rejected() -> None:
    definition = SettingDef("test.dup", 1, int, "test", "Дубль")
    with pytest.raises(SettingValidationError):
        SettingsRegistry([definition, definition])


async def test_module_toggle_created_for_disableable_modules() -> None:
    from aiogram import Router

    from core.registry import ModuleSpec

    registry = build_registry(
        [
            ModuleSpec(name="games", priority=90, router=Router(name="games")),
            ModuleSpec(name="chats", priority=10, router=Router(name="chats"), can_disable=False),
        ]
    )

    assert registry.has("modules.games.enabled")
    assert not registry.has("modules.chats.enabled")


async def test_module_that_cannot_be_disabled_is_always_enabled(session, service) -> None:
    await make_chat(session, CHAT_A)
    assert await service.is_module_enabled(CHAT_A, "chats") is True


async def test_get_many_filters_by_prefix(session, service) -> None:
    await make_chat(session, CHAT_A)
    values = await service.get_many(CHAT_A, "core.")
    assert set(values) == {d.key for d in CORE_SETTINGS}
