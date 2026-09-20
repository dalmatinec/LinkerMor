"""Приветствие новых участников (ТЗ §9)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aiogram.types import Chat as TgChat
from aiogram.types import Message, MessageEntity, PhotoSize
from aiogram.types import User as TgUser

from cache.memory import MemoryCache
from mod_triggers.models import ContentKind
from mod_triggers.repo import ContentRepository
from mod_welcome.service import WelcomeService
from sender.sender import Sender
from sender.throttle import RateLimiter
from settings.defs import build_registry as build_settings
from settings.service import SettingsService
from texts.defs import build_registry as build_texts
from texts.service import TextService
from tests.fakes import FakeBot
from tests.test_chat_repository import make_chat, make_user

CHAT_A = -1001111111111
CHAT_B = -1002222222222
ADMIN_ID = 8243233601
NEWCOMER = TgUser(id=555, is_bot=False, first_name="Новичок", username="newbie")
TG_CHAT = TgChat(id=CHAT_A, type="supergroup", title="Чат A")
EMOJI_ID = "5378621920176607009"


def specs() -> list:
    from core.bootstrap import ENABLED_MODULES

    return ENABLED_MODULES()


class RecordingSender(Sender):
    """Отправитель, запоминающий сообщения вместо обращения к Telegram."""

    def __init__(self) -> None:
        super().__init__(FakeBot(), RateLimiter(chat_interval=0.0))
        self.sent: list[tuple[int, str]] = []
        self.deleted: list[int] = []

    async def send(self, chat_id, content, **kwargs):  # type: ignore[override]
        self.sent.append((chat_id, content.text))

        class _Sent:
            message_id = 100 + len(self.sent)

        return _Sent()

    async def send_media(self, chat_id, kind, file_id, caption=None, **kwargs):  # type: ignore[override]
        self.sent.append((chat_id, f"{kind}:{file_id}"))

        class _Sent:
            message_id = 200

        return _Sent()

    async def delete_message(self, chat_id, message_id):  # type: ignore[override]
        self.deleted.append(message_id)
        return True


@pytest.fixture
def cache() -> MemoryCache:
    return MemoryCache()


@pytest.fixture
def sender() -> RecordingSender:
    return RecordingSender()


@pytest.fixture
def settings(session, cache) -> SettingsService:
    return SettingsService(session, cache, build_settings(specs()))


@pytest.fixture
def texts(session, cache) -> TextService:
    return TextService(session, cache, build_texts(specs()))


@pytest.fixture
def service(session, settings, texts, sender) -> WelcomeService:
    return WelcomeService(session, settings, texts, sender)


def source(text: str = "Привет, {user}!", *, entities=None, photo: bool = False) -> Message:
    return Message(
        message_id=7,
        date=datetime.now(UTC),
        chat=TG_CHAT,
        from_user=NEWCOMER,
        text=None if photo else text,
        entities=None if photo else entities,
        caption=text if photo else None,
        photo=[PhotoSize(file_id="big", file_unique_id="b", width=800, height=800)]
        if photo
        else None,
    )


async def setup(session, chat_id: int = CHAT_A) -> None:
    await make_chat(session, chat_id)
    await make_user(session, ADMIN_ID, "admin")
    await make_user(session, NEWCOMER.id, "newbie")


# ─── Отправка ────────────────────────────────────────────────────────────────


async def test_disabled_welcome_sends_nothing(session, service, sender) -> None:
    await setup(session)

    await service.send(CHAT_A, NEWCOMER, TG_CHAT)

    assert sender.sent == []


async def test_default_text_used_when_nothing_configured(
    session, service, sender, settings
) -> None:
    """Чат не должен оставаться вовсе без реакции на вход."""
    await setup(session)
    await settings.set(CHAT_A, "welcome.enabled", True, ADMIN_ID)

    await service.send(CHAT_A, NEWCOMER, TG_CHAT)

    assert len(sender.sent) == 1
    # У участника есть username, поэтому упоминание выглядит как @newbie.
    assert "@newbie" in sender.sent[0][1]


async def test_custom_welcome_is_used(session, service, sender, settings) -> None:
    await setup(session)
    await settings.set(CHAT_A, "welcome.enabled", True, ADMIN_ID)
    await service.set_from_message(CHAT_A, source("Здравствуй, {user}!"), ADMIN_ID)

    await service.send(CHAT_A, NEWCOMER, TG_CHAT)

    assert sender.sent[0][1] == "Здравствуй, Новичок!"


async def test_welcome_keeps_formatting(session, service, settings) -> None:
    """Премиум-эмодзи переживает сохранение приветствия."""
    await setup(session)
    entity = MessageEntity(type="custom_emoji", offset=0, length=2, custom_emoji_id=EMOJI_ID)

    welcome = await service.set_from_message(
        CHAT_A, source("🔥 Привет, {user}!", entities=[entity]), ADMIN_ID
    )

    assert welcome.content.entities[0]["custom_emoji_id"] == EMOJI_ID


async def test_media_welcome(session, service, sender, settings) -> None:
    await setup(session)
    await settings.set(CHAT_A, "welcome.enabled", True, ADMIN_ID)
    await service.set_from_message(CHAT_A, source("Подпись", photo=True), ADMIN_ID)

    await service.send(CHAT_A, NEWCOMER, TG_CHAT)

    assert sender.sent[0][1] == f"{ContentKind.PHOTO}:big"


async def test_previous_welcome_is_removed(session, service, sender, settings) -> None:
    """Поток входов не должен засорять чат приветствиями."""
    await setup(session)
    await settings.set(CHAT_A, "welcome.enabled", True, ADMIN_ID)
    await service.set_from_message(CHAT_A, source("Привет"), ADMIN_ID)

    await service.send(CHAT_A, NEWCOMER, TG_CHAT)
    await service.send(CHAT_A, NEWCOMER, TG_CHAT)

    assert len(sender.deleted) == 1


async def test_previous_welcome_kept_when_disabled(
    session, service, sender, settings
) -> None:
    await setup(session)
    await settings.set(CHAT_A, "welcome.enabled", True, ADMIN_ID)
    await settings.set(CHAT_A, "welcome.delete_previous", False, ADMIN_ID)
    await service.set_from_message(CHAT_A, source("Привет"), ADMIN_ID)

    await service.send(CHAT_A, NEWCOMER, TG_CHAT)
    await service.send(CHAT_A, NEWCOMER, TG_CHAT)

    assert sender.deleted == []


# ─── Изменение ───────────────────────────────────────────────────────────────


async def test_replacing_welcome_cleans_old_content(session, service) -> None:
    """Старые записи не должны накапливаться при каждом изменении."""
    await setup(session)
    first = await service.set_from_message(CHAT_A, source("Первое"), ADMIN_ID)
    old_content_id = first.content_id

    await service.set_from_message(CHAT_A, source("Второе"), ADMIN_ID)

    assert await ContentRepository(session).get(old_content_id) is None


async def test_clear_removes_welcome(session, service) -> None:
    await setup(session)
    await service.set_from_message(CHAT_A, source("Привет"), ADMIN_ID)

    assert await service.clear(CHAT_A) is True
    assert await service.get(CHAT_A) is None
    assert await service.clear(CHAT_A) is False


# ─── Изоляция ────────────────────────────────────────────────────────────────


async def test_welcome_is_per_chat(session, service, settings, sender) -> None:
    """Пример из ТЗ §22: приветствие включено в A и выключено в B."""
    await setup(session, CHAT_A)
    await setup(session, CHAT_B)
    await settings.set(CHAT_A, "welcome.enabled", True, ADMIN_ID)
    await service.set_from_message(CHAT_A, source("Только в A"), ADMIN_ID)

    await service.send(CHAT_A, NEWCOMER, TG_CHAT)
    await service.send(CHAT_B, NEWCOMER, TgChat(id=CHAT_B, type="supergroup", title="Чат B"))

    assert [chat_id for chat_id, _ in sender.sent] == [CHAT_A]
