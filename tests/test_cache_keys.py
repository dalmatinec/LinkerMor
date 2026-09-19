"""Изоляция чатов на уровне ключей кеша (ТЗ §22, критерий приёмки §32.7)."""

from __future__ import annotations

import pytest

from cache.keys import (
    ChatEntity,
    GlobalEntity,
    chat_key,
    chat_prefix,
    global_key,
)

CHAT_A = -1001111111111
CHAT_B = -1002222222222


def test_chat_key_contains_chat_id() -> None:
    key = chat_key(ChatEntity.SETTINGS, CHAT_A)
    assert str(CHAT_A) in key
    assert key == "lm:v1:settings:-1001111111111"


def test_different_chats_never_share_a_key() -> None:
    for entity in ChatEntity:
        assert chat_key(entity, CHAT_A) != chat_key(entity, CHAT_B)


def test_chat_scoped_entity_cannot_be_used_globally() -> None:
    """Ключ вида ``settings:welcome`` без чата собрать невозможно."""
    with pytest.raises(TypeError):
        global_key(ChatEntity.SETTINGS)  # type: ignore[arg-type]


def test_global_entity_cannot_be_used_as_chat_scoped() -> None:
    with pytest.raises(TypeError):
        chat_key(GlobalEntity.BOT_INFO, CHAT_A)  # type: ignore[arg-type]


def test_entity_sets_do_not_overlap() -> None:
    """Сущность не может быть одновременно чатовой и глобальной."""
    assert not ({e.value for e in ChatEntity} & {e.value for e in GlobalEntity})


def test_chat_prefix_matches_only_its_chat() -> None:
    import fnmatch

    pattern = chat_prefix(CHAT_A)
    assert fnmatch.fnmatchcase(chat_key(ChatEntity.TEXTS, CHAT_A, "ru"), pattern)
    assert not fnmatch.fnmatchcase(chat_key(ChatEntity.TEXTS, CHAT_B, "ru"), pattern)
