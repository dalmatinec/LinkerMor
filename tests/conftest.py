"""Тестовое окружение: бот с поддельной сессией вместо сети.

Поддельная сессия записывает каждый вызов Bot API и отвечает правдоподобно,
поэтому апдейты проходят через настоящий диспетчер, роутеры, фильтры и
middleware — как в бою, только без Telegram.
"""

from __future__ import annotations

import datetime as dt
import itertools
from typing import Any

import pytest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramForbiddenError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import (
    CopyMessage,
    EditMessageText,
    GetMe,
    SendMessage,
    SendPhoto,
)
from aiogram.types import CallbackQuery, Chat, Message, MessageId, Update, User

from bot.broadcast import Broadcaster
from bot.captcha import CaptchaStore
from bot.db import Database
from bot.flood import FloodControl
from bot.handlers import admin, build_router, group, moderation, user
from bot.settings import Settings

OWNER = 1000
STAFF = 2000
GROUP = -100500
BOT_ID = 42


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[Any] = []
        self.blocked: set[int] = set()
        self._ids = itertools.count(1000)

    async def close(self) -> None:  # pragma: no cover
        pass

    async def stream_content(self, *a, **kw):  # pragma: no cover
        raise NotImplementedError

    def _message(self, chat_id: int, **extra: Any) -> Message:
        chat_type = "private" if chat_id > 0 else "supergroup"
        return Message(
            message_id=next(self._ids),
            date=dt.datetime.now(),
            chat=Chat(id=chat_id, type=chat_type),
            from_user=User(id=BOT_ID, is_bot=True, first_name="Bot"),
            **extra,
        )

    async def make_request(self, bot: Bot, method, timeout: int | None = None):
        self.calls.append(method)
        chat_id = getattr(method, "chat_id", None)
        if chat_id in self.blocked:
            raise TelegramForbiddenError(method=method, message="Forbidden: bot was blocked by the user")
        if isinstance(method, GetMe):
            return User(id=BOT_ID, is_bot=True, first_name="Bot", username="test_bot")
        if isinstance(method, CopyMessage):
            return MessageId(message_id=next(self._ids))
        if isinstance(method, (SendMessage, EditMessageText)):
            return self._message(chat_id or 1, text=method.text)
        if isinstance(method, SendPhoto):
            return self._message(chat_id)
        return True

    def of(self, kind: type, chat_id: int | None = None) -> list[Any]:
        return [
            c for c in self.calls
            if isinstance(c, kind) and (chat_id is None or c.chat_id == chat_id)
        ]


class Harness:
    def __init__(self, bot: Bot, dp: Dispatcher, session: FakeSession, db: Database, settings: Settings):
        self.bot, self.dp, self.session, self.db, self.settings = bot, dp, session, db, settings
        self._updates = itertools.count(1)
        self._msgs = itertools.count(1)

    async def feed(self, event: Message | CallbackQuery) -> None:
        key = "message" if isinstance(event, Message) else "callback_query"
        await self.dp.feed_update(self.bot, Update(update_id=next(self._updates), **{key: event}))

    def message(
        self,
        user_id: int,
        text: str | None = "привет",
        chat_id: int | None = None,
        reply_to: int | None = None,
        **extra: Any,
    ) -> Message:
        chat_id = chat_id if chat_id is not None else user_id
        chat_type = "private" if chat_id > 0 else "supergroup"
        reply = None
        if reply_to is not None:
            reply = Message(
                message_id=reply_to, date=dt.datetime.now(),
                chat=Chat(id=chat_id, type=chat_type),
                from_user=User(id=BOT_ID, is_bot=True, first_name="Bot"),
                text="…",
            )
        return Message(
            message_id=next(self._msgs),
            date=dt.datetime.now(),
            chat=Chat(id=chat_id, type=chat_type),
            from_user=User(id=user_id, is_bot=False, first_name=f"U{user_id}", username=f"u{user_id}"),
            text=text,
            reply_to_message=reply,
            **extra,
        )

    def callback(self, user_id: int, data: str, chat_id: int | None = None) -> CallbackQuery:
        chat_id = chat_id if chat_id is not None else user_id
        msg = self.session._message(chat_id, text="panel")
        return CallbackQuery(
            id=str(next(self._updates)),
            from_user=User(id=user_id, is_bot=False, first_name=f"U{user_id}"),
            chat_instance="ci",
            message=msg,
            data=data,
        )

    async def start_and_pass(self, user_id: int) -> None:
        await self.feed(self.message(user_id, "/start"))
        store: CaptchaStore = self.dp["captchas"]
        ch = store.get(user_id)
        if ch is not None:
            await self.feed(self.callback(user_id, f"cap:{ch.answer}"))


@pytest_asyncio.fixture
async def db():
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


@pytest_asyncio.fixture
async def h(db):
    settings = Settings(db, frozenset({OWNER}))
    await settings.load()
    await settings.set("group_id", GROUP)
    session = FakeSession()
    bot = Bot("42:TEST", session=session)
    # Роутеры модулей — синглтоны, а диспетчер в каждом тесте новый.
    for r in (admin.router, moderation.router, group.router, user.router):
        r._parent_router = None
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(build_router())
    dp["db"] = db
    dp["settings"] = settings
    dp["flood"] = FloodControl()
    dp["captchas"] = CaptchaStore()
    dp["broadcaster"] = Broadcaster(rate=1000)
    return Harness(bot, dp, session, db, settings)
