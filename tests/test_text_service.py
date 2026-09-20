"""Система текстов: цепочка резолва, подстановка, изоляция (ТЗ §13)."""

from __future__ import annotations

import pytest

from cache.memory import MemoryCache
from core.errors import LinkerMorError, SettingValidationError
from texts.defs import CORE_TEXTS, TextDef, TextRegistry
from texts.entities import Entity, EntityText
from texts.service import TextService
from tests.test_chat_repository import make_chat

CHAT_A = -1001111111111
CHAT_B = -1002222222222
ACTOR = 8243233601
EMOJI_ID = "5378621920176607009"


@pytest.fixture
def registry() -> TextRegistry:
    return TextRegistry(
        [
            *CORE_TEXTS,
            TextDef("ban_success", "{user} забанен. Причина: {reason}", "moderation", "Бан выдан"),
        ]
    )


@pytest.fixture
def cache() -> MemoryCache:
    return MemoryCache()


@pytest.fixture
def service(session, cache, registry) -> TextService:
    return TextService(session, cache, registry)


# ─── Цепочка резолва ─────────────────────────────────────────────────────────


async def test_default_is_used_when_nothing_overridden(service) -> None:
    text = await service.get(CHAT_A, "permission_denied")
    assert text.text == "У вас нет прав для этого действия."


async def test_global_override_beats_default(session, service) -> None:
    await make_chat(session, CHAT_A)
    await service.set_global("permission_denied", EntityText(text="Нельзя."), ACTOR)

    assert (await service.get(CHAT_A, "permission_denied")).text == "Нельзя."
    assert await service.source_of(CHAT_A, "permission_denied") == "global"


async def test_chat_override_beats_global(session, service) -> None:
    await make_chat(session, CHAT_A)
    await service.set_global("permission_denied", EntityText(text="Глобально нельзя."), ACTOR)
    await service.set_for_chat(CHAT_A, "permission_denied", EntityText(text="Тут нельзя."), ACTOR)

    assert (await service.get(CHAT_A, "permission_denied")).text == "Тут нельзя."
    assert await service.source_of(CHAT_A, "permission_denied") == "chat"


async def test_reset_falls_back_to_global(session, service) -> None:
    await make_chat(session, CHAT_A)
    await service.set_global("permission_denied", EntityText(text="Глобально."), ACTOR)
    await service.set_for_chat(CHAT_A, "permission_denied", EntityText(text="Локально."), ACTOR)

    restored = await service.reset_for_chat(CHAT_A, "permission_denied")

    assert restored.text == "Глобально."


async def test_unknown_text_key_is_rejected(service) -> None:
    with pytest.raises(LinkerMorError):
        await service.get(CHAT_A, "выдуманный_ключ")


# ─── Подстановка ─────────────────────────────────────────────────────────────


async def test_render_substitutes_values(service) -> None:
    rendered = await service.render(
        CHAT_A, "ban_success", {"user": "Нарушитель", "reason": "спам"}
    )
    assert rendered.text == "Нарушитель забанен. Причина: спам"


async def test_render_never_shows_raw_placeholder(service) -> None:
    """Критерий приёмки §32.18: {...} не должен попасть пользователю."""
    rendered = await service.render(CHAT_A, "ban_success", {"user": "Нарушитель"})

    assert "{" not in rendered.text
    assert rendered.text == "Нарушитель забанен. Причина: "


async def test_text_with_unknown_placeholder_is_rejected_on_save(session, service) -> None:
    """Опечатку администратор должен увидеть сразу, а не в пустом сообщении."""
    await make_chat(session, CHAT_A)

    with pytest.raises(SettingValidationError, match="Неизвестные плейсхолдеры"):
        await service.set_for_chat(
            CHAT_A, "ban_success", EntityText(text="{user} забанен {typo_key}"), ACTOR
        )


async def test_formatting_survives_storage_and_render(session, service) -> None:
    """Премиум-эмодзи и жирный должны пережить запись, чтение и подстановку."""
    await make_chat(session, CHAT_A)
    template = EntityText(
        text="🔥 {user} забанен",
        entities=(
            Entity("custom_emoji", 0, 1, custom_emoji_id=EMOJI_ID),
            Entity("bold", 2, 6),
        ),
    )
    await service.set_for_chat(CHAT_A, "ban_success", template, ACTOR)

    rendered = await service.render(CHAT_A, "ban_success", {"user": "Нарушитель"})
    text, entities = rendered.to_telegram()

    assert text == "🔥 Нарушитель забанен"
    emoji = next(e for e in entities if e.type == "custom_emoji")
    bold = next(e for e in entities if e.type == "bold")
    assert emoji.custom_emoji_id == EMOJI_ID
    assert emoji.offset == 0 and emoji.length == 2
    # Позиции Telegram считаются в UTF-16, а текст индексируется по символам:
    # проверяем через внутренние позиции, а границу UTF-16 — отдельно.
    inner_bold = next(e for e in rendered.entities if e.type == "bold")
    assert rendered.text[inner_bold.offset : inner_bold.end] == "Нарушитель"
    assert bold.offset == 3  # эмодзи занимает две единицы, пробел — одну


# ─── Изоляция ────────────────────────────────────────────────────────────────


async def test_chat_text_does_not_leak_to_another_chat(session, service) -> None:
    await make_chat(session, CHAT_A)
    await make_chat(session, CHAT_B)

    await service.set_for_chat(CHAT_A, "ban_success", EntityText(text="Только для A"), ACTOR)

    assert (await service.get(CHAT_A, "ban_success")).text == "Только для A"
    assert (await service.get(CHAT_B, "ban_success")).text.startswith("{user} забанен")


async def test_global_change_reaches_chats_without_override(session, service) -> None:
    """Владелец меняет текст глобально — чаты без своей версии видят новый."""
    await make_chat(session, CHAT_A)
    await make_chat(session, CHAT_B)
    await service.set_for_chat(CHAT_A, "permission_denied", EntityText(text="Своё"), ACTOR)
    # Прогреваем кеш обоих чатов.
    await service.get(CHAT_A, "permission_denied")
    await service.get(CHAT_B, "permission_denied")

    await service.set_global("permission_denied", EntityText(text="Новое общее"), ACTOR)

    assert (await service.get(CHAT_A, "permission_denied")).text == "Своё"
    assert (await service.get(CHAT_B, "permission_denied")).text == "Новое общее"


async def test_every_registered_text_resolves(service, registry) -> None:
    """Ни один объявленный текст не должен оказаться пустым."""
    for key in registry.keys:
        assert (await service.get(CHAT_A, key)).text


async def test_braces_that_are_not_placeholders_are_left_alone(service) -> None:
    """Плейсхолдеры — латиница: прочий текст в скобках остаётся как есть."""
    source = EntityText(text="Скидка {50%} и {приз}")
    assert source.placeholders() == set()
    assert source.render({}).text == "Скидка {50%} и {приз}"
