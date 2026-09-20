"""Прогон сообщения через весь конвейер обработки.

Проверяет то, что не видно при тестировании сервисов по отдельности: в
aiogram первый подошедший хендлер останавливает цепочку. Сборщик
активности, подписанный на все сообщения, перехватывал бы их и не давал
работать антиспаму, триггерам, репутации и рангам.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat as TgChat
from aiogram.types import Message, Update
from aiogram.types import User as TgUser

from cache.memory import MemoryCache
from core.bootstrap import ENABLED_MODULES
from core.config import Settings
from core.registry import build_registry as build_modules
from middlewares.activity import ActivityMiddleware
from middlewares.chat_context import ChatContextMiddleware
from middlewares.db_session import DbSessionMiddleware
from middlewares.services import ServicesMiddleware
from mod_chats.repo import MemberRepository
from mod_stats.repo import StatsRepository
from settings.defs import build_registry as build_settings
from settings.service import SettingsService
from texts.defs import build_registry as build_texts
from tests.conftest import FAKE_TOKEN
from tests.fakes import FakeBot
from tests.test_chat_repository import make_chat, make_user
from tests.test_welcome import RecordingSender

CHAT_ID = -1001111111111
USER = TgUser(id=555, is_bot=False, first_name="Участник", username="member")
TG_CHAT = TgChat(id=CHAT_ID, type="supergroup", title="Чат")


@pytest.fixture
def cache() -> MemoryCache:
    return MemoryCache()


@pytest.fixture
def config() -> Settings:
    return Settings(_env_file=None, bot_token=FAKE_TOKEN, owner_ids_raw="1")


@pytest.fixture
def sender() -> RecordingSender:
    return RecordingSender()


@pytest.fixture
def dispatcher(session_factory, cache, config, sender) -> Dispatcher:
    """Диспетчер, собранный так же, как в рабочем приложении."""
    specs = ENABLED_MODULES()
    settings_registry = build_settings(specs)
    text_registry = build_texts(specs)

    # Роутеры объявлены на уровне модулей и живут в одном экземпляре.
    # Повторное подключение к новому диспетчеру aiogram запрещает, поэтому
    # перед сборкой связь с прежним диспетчером снимается.
    for spec in specs:
        spec.router._parent_router = None

    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.update.outer_middleware(DbSessionMiddleware(session_factory))
    dispatcher.update.outer_middleware(ChatContextMiddleware())
    dispatcher.update.outer_middleware(ActivityMiddleware())
    dispatcher.update.outer_middleware(
        ServicesMiddleware(config, cache, settings_registry, text_registry, sender)
    )
    dispatcher["cache"] = cache
    build_modules(specs).attach(dispatcher)
    return dispatcher


def update(text: str, update_id: int = 1) -> Update:
    return Update(
        update_id=update_id,
        message=Message(
            message_id=update_id + 100,
            date=datetime.now(UTC),
            chat=TG_CHAT,
            from_user=USER,
            text=text,
        ),
    )


async def prepare(session_factory, *, admin: bool = False) -> None:
    from core.constants import Role

    async with session_factory() as session:
        await make_chat(session, CHAT_ID)
        await make_user(session, USER.id, "member")
        if admin:
            await MemberRepository(session).upsert(
                chat_id=CHAT_ID, user_id=USER.id, role=Role.CHAT_ADMIN,
                tg_status="administrator",
            )
        await session.commit()


async def test_ordinary_message_reaches_the_end_of_the_pipeline(
    dispatcher, session_factory, sender
) -> None:
    """Сообщение без нарушений должно пройти всю цепочку.

    Именно этот случай ломался: сборщик активности возвращал управление и
    останавливал обработку, а значит триггеры и репутация не работали бы
    вовсе.
    """
    await prepare(session_factory)
    bot = FakeBot()

    await dispatcher.feed_update(bot, update("обычное сообщение"))

    async with session_factory() as session:
        member = await MemberRepository(session).get(CHAT_ID, USER.id)
        messages = await StatsRepository(session).messages_since(
            CHAT_ID, datetime.now(UTC).date()
        )

    assert member is not None
    assert member.messages_total == 1, "активность не учтена"
    assert messages == 1, "статистика не собрана"


async def test_trigger_fires_after_activity_is_counted(
    dispatcher, session_factory, cache, sender
) -> None:
    """Триггер обязан сработать, несмотря на более ранние обработчики."""
    await prepare(session_factory)
    from mod_triggers.service import TriggerService

    async with session_factory() as session:
        await TriggerService(session, cache).add(
            CHAT_ID, "привет", text="Здравствуйте!", actor_id=USER.id
        )
        await session.commit()

    await dispatcher.feed_update(FakeBot(), update("всем привет"))

    assert any("Здравствуйте" in text for _, text in sender.sent), (
        "триггер не сработал: сообщение перехвачено более ранним обработчиком"
    )

    async with session_factory() as session:
        member = await MemberRepository(session).get(CHAT_ID, USER.id)
    assert member.messages_total == 1, "активность потеряна из-за срабатывания триггера"


async def test_antispam_stops_pipeline_when_it_acts(
    dispatcher, session_factory, cache, config, sender
) -> None:
    """Сработавшее правило останавливает цепочку: триггер не отвечает."""
    await prepare(session_factory)
    from mod_antispam.repo import WordRepository
    from mod_triggers.service import TriggerService

    specs = ENABLED_MODULES()
    async with session_factory() as session:
        settings = SettingsService(session, cache, build_settings(specs))
        await settings.set(CHAT_ID, "antispam.words.enabled", True, USER.id)
        await settings.set(CHAT_ID, "core.staff_immune", False, USER.id)
        await WordRepository(session).add(CHAT_ID, "реклама", USER.id)
        await TriggerService(session, cache).add(
            CHAT_ID, "реклама", text="Ответ триггера", actor_id=USER.id
        )
        await session.commit()

    await dispatcher.feed_update(FakeBot(), update("тут реклама"))

    assert not any("Ответ триггера" in text for _, text in sender.sent), (
        "триггер ответил на сообщение, удалённое антиспамом"
    )


async def test_command_is_not_swallowed_by_collectors(
    dispatcher, session_factory, sender
) -> None:
    """Команда должна дойти до своего модуля, а не до сборщика активности."""
    await prepare(session_factory, admin=True)

    await dispatcher.feed_update(FakeBot(), update("/lw"))

    assert sender.sent, "команда осталась без ответа"
