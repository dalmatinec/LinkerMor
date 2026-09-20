"""Фильтры по типу чата работают и для нажатий кнопок."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aiogram.types import CallbackQuery, Chat, Message
from aiogram.types import User as TgUser

from guards.chat_type import InGroup, InPrivate, chat_type_of

USER = TgUser(id=1, is_bot=False, first_name="Тест")
PRIVATE = Chat(id=1, type="private")
GROUP = Chat(id=-100, type="supergroup", title="Чат")


def message_in(chat: Chat) -> Message:
    return Message(message_id=1, date=datetime.now(UTC), chat=chat, from_user=USER, text="меню")


def click_in(chat: Chat) -> CallbackQuery:
    return CallbackQuery(
        id="1", from_user=USER, chat_instance="x", message=message_in(chat), data="test"
    )


@pytest.mark.parametrize("event", [message_in(PRIVATE), click_in(PRIVATE)])
async def test_private_filter_accepts_messages_and_clicks(event) -> None:
    """Нажатие кнопки не имеет поля chat, но относится к чату своего сообщения.

    Пока это не учитывалось, ни одна кнопка панели не работала: фильтр
    отсекал все нажатия подряд.
    """
    assert await InPrivate()(event) is True
    assert await InGroup()(event) is False


@pytest.mark.parametrize("event", [message_in(GROUP), click_in(GROUP)])
async def test_group_filter_accepts_messages_and_clicks(event) -> None:
    assert await InGroup()(event) is True
    assert await InPrivate()(event) is False


async def test_click_without_message_is_not_matched() -> None:
    """У старого нажатия сообщение может быть недоступно."""
    orphan = CallbackQuery(id="1", from_user=USER, chat_instance="x", data="test")

    assert chat_type_of(orphan) is None
    assert await InPrivate()(orphan) is False
    assert await InGroup()(orphan) is False
