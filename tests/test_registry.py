"""Реестр модулей: порядок обработки задан явно и конфликты невозможны."""

from __future__ import annotations

import pytest
from aiogram import Router

from core.errors import ModuleRegistrationError
from core.registry import ModuleSpec, build_registry


def spec(name: str, priority: int, **kwargs) -> ModuleSpec:
    return ModuleSpec(name=name, priority=priority, router=Router(name=name), **kwargs)


def test_modules_ordered_by_priority() -> None:
    registry = build_registry([spec("games", 90), spec("chats", 10), spec("moderation", 50)])
    assert registry.names == ("chats", "moderation", "games")


def test_duplicate_name_rejected() -> None:
    with pytest.raises(ModuleRegistrationError, match="дважды"):
        build_registry([spec("triggers", 10), spec("triggers", 20)])


def test_duplicate_priority_rejected() -> None:
    """Одинаковый приоритет означал бы неопределённый порядок обработки."""
    with pytest.raises(ModuleRegistrationError, match="priority"):
        build_registry([spec("triggers", 10), spec("welcome", 10)])


def test_invalid_module_name_rejected() -> None:
    with pytest.raises(ModuleRegistrationError):
        spec("не имя!", 10)


def test_disableable_modules_listed() -> None:
    registry = build_registry([spec("chats", 10, can_disable=False), spec("games", 90)])
    assert registry.disableable == ("games",)


def test_lookup_of_unknown_module_fails_loudly() -> None:
    registry = build_registry([spec("chats", 10)])
    with pytest.raises(ModuleRegistrationError):
        registry.get("welcome")
