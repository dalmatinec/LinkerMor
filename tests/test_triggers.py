"""Триггеры: создание из сообщения, хранение оформления, изоляция (ТЗ §8)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aiogram.types import Chat as TgChat
from aiogram.types import Message, MessageEntity, PhotoSize
from aiogram.types import User as TgUser

from cache.keys import ChatEntity, chat_key
from cache.memory import MemoryCache
from core.constants import Role
from core.errors import PermissionDenied
from mod_triggers.content import UnsupportedContent, extract
from mod_triggers.models import ContentKind, MatchType
from mod_triggers.service import TriggerExists, TriggerService
from tests.test_chat_repository import make_chat, make_user

CHAT_A = -1001111111111
CHAT_B = -1002222222222
ADMIN_ID = 8243233601
EMOJI_ID = "5378621920176607009"

TG_CHAT = TgChat(id=CHAT_A, type="supergroup", title="Чат")
AUTHOR = TgUser(id=ADMIN_ID, is_bot=False, first_name="Админ", username="admin")


def source_message(
    text: str | None = "Ответ триггера",
    *,
    entities=None,
    photo: bool = False,
    caption: str | None = None,
) -> Message:
    return Message(
        message_id=7,
        date=datetime.now(UTC),
        chat=TG_CHAT,
        from_user=AUTHOR,
        text=None if photo else text,
        entities=None if photo else entities,
        caption=caption if photo else None,
        caption_entities=entities if photo else None,
        photo=(
            [
                PhotoSize(file_id="small", file_unique_id="s", width=90, height=90),
                PhotoSize(file_id="large", file_unique_id="l", width=800, height=800),
            ]
            if photo
            else None
        ),
    )


@pytest.fixture
def cache() -> MemoryCache:
    return MemoryCache()


@pytest.fixture
def service(session, cache) -> TriggerService:
    return TriggerService(session, cache)


async def setup(session, chat_id: int = CHAT_A) -> None:
    await make_chat(session, chat_id)
    await make_user(session, ADMIN_ID, "admin")


# ─── Извлечение контента ─────────────────────────────────────────────────────


def test_extract_plain_text() -> None:
    fields = extract(source_message("Просто текст"))

    assert fields["kind"] == ContentKind.TEXT
    assert fields["text"] == "Просто текст"
    assert fields["file_id"] is None


def test_extract_keeps_formatting() -> None:
    """Премиум-эмодзи обязан пережить сохранение."""
    entity = MessageEntity(type="custom_emoji", offset=0, length=2, custom_emoji_id=EMOJI_ID)

    fields = extract(source_message("🔥 Привет", entities=[entity]))

    assert fields["entities"][0]["custom_emoji_id"] == EMOJI_ID


def test_extract_photo_takes_largest_size() -> None:
    fields = extract(source_message(photo=True, caption="Подпись"))

    assert fields["kind"] == ContentKind.PHOTO
    assert fields["file_id"] == "large"
    assert fields["text"] == "Подпись"


def test_extract_rejects_empty_message() -> None:
    with pytest.raises(UnsupportedContent):
        extract(source_message(None))


# ─── Создание и удаление ─────────────────────────────────────────────────────


async def test_add_from_reply(session, service) -> None:
    await setup(session)

    trigger = await service.add(CHAT_A, "Привет", source=source_message(), actor_id=ADMIN_ID)

    assert trigger.key == "привет"  # хранится нормализованным
    assert trigger.display_key == "Привет"  # показывается как ввели
    assert trigger.content.text == "Ответ триггера"


async def test_add_from_inline_text(session, service) -> None:
    await setup(session)

    trigger = await service.add(CHAT_A, "правила", text="Читайте закреп", actor_id=ADMIN_ID)

    assert trigger.content.text == "Читайте закреп"


async def test_duplicate_key_rejected(session, service) -> None:
    await setup(session)
    await service.add(CHAT_A, "привет", source=source_message(), actor_id=ADMIN_ID)

    with pytest.raises(TriggerExists):
        await service.add(CHAT_A, "ПРИВЕТ", source=source_message(), actor_id=ADMIN_ID)


async def test_remove(session, service) -> None:
    await setup(session)
    await service.add(CHAT_A, "привет", source=source_message(), actor_id=ADMIN_ID)

    assert await service.remove(CHAT_A, "Привет") is True
    assert await service.remove(CHAT_A, "привет") is False


async def test_regex_requires_owner(session, service) -> None:
    """Регулярное выражение способно занять процессор надолго."""
    await setup(session)

    with pytest.raises(PermissionDenied):
        await service.add(
            CHAT_A, r"куп(ить|лю)", text="ответ", match_type=MatchType.REGEX,
            actor_id=ADMIN_ID, actor_role=Role.CHAT_ADMIN,
        )

    trigger = await service.add(
        CHAT_A, r"куп(ить|лю)", text="ответ", match_type=MatchType.REGEX,
        actor_id=ADMIN_ID, actor_role=Role.BOT_OWNER,
    )
    assert trigger.match_type == MatchType.REGEX


# ─── Поиск ───────────────────────────────────────────────────────────────────


async def test_find_returns_trigger(session, service) -> None:
    await setup(session)
    await service.add(CHAT_A, "привет", source=source_message(), actor_id=ADMIN_ID)

    found = await service.find(CHAT_A, "Всем привет!")

    assert found is not None
    assert found.key == "привет"


async def test_find_counts_hits(session, service) -> None:
    await setup(session)
    await service.add(CHAT_A, "привет", source=source_message(), actor_id=ADMIN_ID)

    await service.find(CHAT_A, "привет")
    await service.find(CHAT_A, "привет")
    session.expire_all()

    triggers = await service.list_all(CHAT_A)
    assert triggers[0].hits == 2


async def test_disabled_trigger_does_not_fire(session, service) -> None:
    await setup(session)
    await service.add(CHAT_A, "привет", source=source_message(), actor_id=ADMIN_ID)
    await service.set_enabled(CHAT_A, "привет", False)

    assert await service.find(CHAT_A, "привет") is None


# ─── Кеш ─────────────────────────────────────────────────────────────────────


async def test_rules_are_cached_per_chat(session, cache, service) -> None:
    await setup(session)
    await service.add(CHAT_A, "привет", source=source_message(), actor_id=ADMIN_ID)

    await service.rules(CHAT_A)

    assert await cache.get(chat_key(ChatEntity.TRIGGERS, CHAT_A)) is not None
    assert await cache.get(chat_key(ChatEntity.TRIGGERS, CHAT_B)) is None


async def test_cache_is_dropped_on_change(session, cache, service) -> None:
    """Иначе новый триггер не сработал бы до истечения срока кеша."""
    await setup(session)
    await service.rules(CHAT_A)

    await service.add(CHAT_A, "привет", source=source_message(), actor_id=ADMIN_ID)

    assert await cache.get(chat_key(ChatEntity.TRIGGERS, CHAT_A)) is None
    assert await service.find(CHAT_A, "привет") is not None


async def test_cooldown_blocks_repeat(session, cache, service) -> None:
    """Пауза не даёт превратить триггер в инструмент флуда."""
    await setup(session)
    trigger = await service.add(CHAT_A, "привет", source=source_message(), actor_id=ADMIN_ID)
    trigger.cooldown = 60
    await session.flush()
    await service.invalidate(CHAT_A)

    assert await service.find(CHAT_A, "привет") is not None
    assert await service.find(CHAT_A, "привет") is None


# ─── Изоляция ────────────────────────────────────────────────────────────────


async def test_triggers_do_not_leak_between_chats(session, service) -> None:
    """Критерий приёмки §32.8."""
    await setup(session, CHAT_A)
    await setup(session, CHAT_B)
    await service.add(CHAT_A, "привет", source=source_message(), actor_id=ADMIN_ID)

    assert await service.find(CHAT_A, "привет") is not None
    assert await service.find(CHAT_B, "привет") is None


async def test_same_key_can_differ_between_chats(session, service) -> None:
    await setup(session, CHAT_A)
    await setup(session, CHAT_B)

    await service.add(CHAT_A, "правила", text="Правила чата A", actor_id=ADMIN_ID)
    await service.add(CHAT_B, "правила", text="Правила чата B", actor_id=ADMIN_ID)

    in_a = await service.find(CHAT_A, "правила")
    in_b = await service.find(CHAT_B, "правила")
    assert in_a.content.text == "Правила чата A"
    assert in_b.content.text == "Правила чата B"


async def test_deleted_trigger_cleans_its_content(session, service) -> None:
    """Сообщения-ответы не должны накапливаться после удаления триггеров."""
    from mod_triggers.repo import ContentRepository

    await setup(session)
    trigger = await service.add(CHAT_A, "привет", source=source_message(), actor_id=ADMIN_ID)
    content_id = trigger.content_id

    await service.remove(CHAT_A, "привет")

    assert await ContentRepository(session).get(content_id) is None


async def test_response_keeps_formatting_end_to_end(session, service) -> None:
    """Сохранили сообщение с премиум-эмодзи — отдали его же."""
    await setup(session)
    entity = MessageEntity(type="custom_emoji", offset=0, length=2, custom_emoji_id=EMOJI_ID)
    await service.add(
        CHAT_A, "привет", source=source_message("🔥 Здравствуйте", entities=[entity]),
        actor_id=ADMIN_ID,
    )

    trigger = await service.find(CHAT_A, "привет")
    kind, body, file_id, keyboard = TriggerService.response_of(trigger)
    text, entities = body.to_telegram()

    assert kind == ContentKind.TEXT
    assert text == "🔥 Здравствуйте"
    assert entities[0].custom_emoji_id == EMOJI_ID
