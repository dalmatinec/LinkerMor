"""Обязательный сценарий приёмки (ТЗ §31, критерии §32.2, §32.9, §32.10).

    Изменить настройку чата A.
    Проверить: чат A получил новое значение, чат B не изменился.
    Перезапустить приложение.
    Проверить: чат A сохранил новое значение, чат B — своё.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from cache.keys import ChatEntity, chat_key
from cache.memory import MemoryCache
from settings.defs import CORE_SETTINGS, SettingsRegistry
from settings.service import SettingsService
from tests.conftest import TEST_DATABASE_URL
from tests.test_chat_repository import make_chat

CHAT_A = -1001111111111
CHAT_B = -1002222222222
ACTOR = 8243233601
SETTING = "core.staff_immune"


def _registry() -> SettingsRegistry:
    return SettingsRegistry(list(CORE_SETTINGS))


async def test_setting_change_is_isolated_and_survives_restart(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    registry = _registry()

    # ── Подготовка: два чата со значениями по умолчанию ──────────────────
    async with session_factory() as session:
        await make_chat(session, CHAT_A, "Чат A")
        await make_chat(session, CHAT_B, "Чат B")
        await session.commit()

    cache = MemoryCache()

    # ── Шаг 1: меняем настройку только в чате A ──────────────────────────
    async with session_factory() as session:
        service = SettingsService(session, cache, registry)
        assert await service.get(CHAT_A, SETTING) is True
        assert await service.get(CHAT_B, SETTING) is True

        await service.set(CHAT_A, SETTING, False, ACTOR)
        await session.commit()

    # ── Шаг 2: A изменился, B не затронут ────────────────────────────────
    async with session_factory() as session:
        service = SettingsService(session, cache, registry)
        assert await service.get(CHAT_A, SETTING) is False
        assert await service.get(CHAT_B, SETTING) is True

    # ── Шаг 3: перезапуск приложения ─────────────────────────────────────
    # Новое подключение к базе и пустой кеш — состояние процесса потеряно
    # полностью, как после рестарта.
    fresh_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    fresh_factory = async_sessionmaker(bind=fresh_engine, class_=AsyncSession)
    fresh_cache = MemoryCache()
    try:
        async with fresh_factory() as session:
            service = SettingsService(session, fresh_cache, _registry())

            # ── Шаг 4: значения на месте ─────────────────────────────────
            assert await service.get(CHAT_A, SETTING) is False, "чат A потерял настройку"
            assert await service.get(CHAT_B, SETTING) is True, "чат B изменился вместе с A"
    finally:
        await fresh_engine.dispose()


async def test_cache_of_one_chat_is_dropped_without_touching_another(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Сброс кеша при записи не должен затрагивать соседние чаты (§32.7)."""
    registry = _registry()
    cache = MemoryCache()

    async with session_factory() as session:
        await make_chat(session, CHAT_A, "Чат A")
        await make_chat(session, CHAT_B, "Чат B")
        await session.commit()

    async with session_factory() as session:
        service = SettingsService(session, cache, registry)
        await service.all(CHAT_A)
        await service.all(CHAT_B)
        assert await cache.get(chat_key(ChatEntity.SETTINGS, CHAT_B)) is not None

        await service.set(CHAT_A, SETTING, False, ACTOR)
        await session.commit()

    assert await cache.get(chat_key(ChatEntity.SETTINGS, CHAT_A)) is None
    assert await cache.get(chat_key(ChatEntity.SETTINGS, CHAT_B)) is not None


async def test_many_chats_keep_independent_values(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Один процесс обслуживает десятки чатов, и каждый со своим значением."""
    registry = _registry()
    cache = MemoryCache()
    chat_ids = [-1000000000000 - index for index in range(10)]

    async with session_factory() as session:
        for index, chat_id in enumerate(chat_ids):
            await make_chat(session, chat_id, f"Чат {index}")
        await session.commit()

    async with session_factory() as session:
        service = SettingsService(session, cache, registry)
        # Чётным чатам выключаем иммунитет администрации, нечётные не трогаем.
        for index, chat_id in enumerate(chat_ids):
            if index % 2 == 0:
                await service.set(chat_id, SETTING, False, ACTOR)
        await session.commit()

    async with session_factory() as session:
        service = SettingsService(session, cache, registry)
        values = [await service.get(chat_id, SETTING) for chat_id in chat_ids]

    assert values == [index % 2 != 0 for index in range(10)]
