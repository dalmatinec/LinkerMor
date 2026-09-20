"""Поведение кеша в памяти."""

from __future__ import annotations

import time

from cache.backend import CacheBackend
from cache.keys import ChatEntity, chat_key, chat_prefix
from cache.memory import MemoryCache

CHAT_A = -1001111111111
CHAT_B = -1002222222222


def test_memory_cache_satisfies_backend_protocol(cache: MemoryCache) -> None:
    assert isinstance(cache, CacheBackend)


async def test_set_and_get(cache: MemoryCache) -> None:
    await cache.set("k", {"a": 1})
    assert await cache.get("k") == {"a": 1}
    assert await cache.get("missing") is None


async def test_ttl_expires(cache: MemoryCache, monkeypatch) -> None:
    await cache.set("k", "v", ttl=10)
    assert await cache.get("k") == "v"

    real = time.monotonic()
    monkeypatch.setattr(time, "monotonic", lambda: real + 11)
    assert await cache.get("k") is None


async def test_invalidating_one_chat_leaves_the_other_intact(cache: MemoryCache) -> None:
    """Сброс кеша чата A не должен затрагивать чат B."""
    await cache.set(chat_key(ChatEntity.SETTINGS, CHAT_A), {"welcome": True})
    await cache.set(chat_key(ChatEntity.TEXTS, CHAT_A, "ru"), {"ban": "ok"})
    await cache.set(chat_key(ChatEntity.SETTINGS, CHAT_B), {"welcome": False})

    removed = await cache.delete_pattern(chat_prefix(CHAT_A))

    assert removed == 2
    assert await cache.get(chat_key(ChatEntity.SETTINGS, CHAT_A)) is None
    assert await cache.get(chat_key(ChatEntity.SETTINGS, CHAT_B)) == {"welcome": False}


async def test_purge_expired(cache: MemoryCache, monkeypatch) -> None:
    await cache.set("alive", 1)
    await cache.set("dying", 2, ttl=5)
    real = time.monotonic()
    monkeypatch.setattr(time, "monotonic", lambda: real + 6)

    assert cache.purge_expired() == 1
    assert len(cache) == 1
