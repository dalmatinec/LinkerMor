"""Разбор аргументов команд модерации."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from aiogram.types import Chat as TgChat
from aiogram.types import Message, MessageEntity
from aiogram.types import User as TgUser

from mod_moderation.handlers import _split_duration, _target_and_rest
from resolver.user_resolver import TargetSource, UserResolver
from tests.test_chat_repository import make_user

CHAT = TgChat(id=-1001111111111, type="supergroup", title="Чат")
ADMIN = TgUser(id=8243233601, is_bot=False, first_name="Админ", username="admin")
SPAMMER = TgUser(id=555, is_bot=False, first_name="Нарушитель", username="spammer")
NO_USERNAME = TgUser(id=777, is_bot=False, first_name="Тихоня")


def command(text: str, *, reply: bool = False, entities=None) -> Message:
    replied = (
        Message(message_id=1, date=datetime.now(UTC), chat=CHAT, from_user=SPAMMER, text="спам")
        if reply
        else None
    )
    return Message(
        message_id=2,
        date=datetime.now(UTC),
        chat=CHAT,
        from_user=ADMIN,
        text=text,
        entities=entities,
        reply_to_message=replied,
    )


@pytest.mark.parametrize(
    ("rest", "duration", "reason"),
    [
        ("2h спам", timedelta(hours=2), "спам"),
        ("30m", timedelta(minutes=30), ""),
        ("спам и флуд", None, "спам и флуд"),
        ("", None, ""),
        ("навсегда нарушение", None, "нарушение"),
    ],
)
def test_duration_is_separated_from_reason(
    rest: str, duration: timedelta | None, reason: str
) -> None:
    """Если первое слово не срок, вся строка считается причиной."""
    assert _split_duration(rest) == (duration, reason)


def test_number_without_unit_is_minutes() -> None:
    assert _split_duration("45 флуд") == (timedelta(minutes=45), "флуд")


async def test_reply_takes_target_and_whole_rest_is_reason(session) -> None:
    await make_user(session, SPAMMER.id, "spammer")

    target, rest = await _target_and_rest(
        UserResolver(session), command("/ban спам и флуд", reply=True), "спам и флуд"
    )

    assert target.id == SPAMMER.id
    assert target.source is TargetSource.REPLY
    assert rest == "спам и флуд"


async def test_without_reply_first_argument_is_target(session) -> None:
    await make_user(session, SPAMMER.id, "spammer")

    target, rest = await _target_and_rest(
        UserResolver(session), command("/ban @spammer спам"), "@spammer спам"
    )

    assert target.id == SPAMMER.id
    assert rest == "спам"


async def test_mention_without_username_is_recognised(session) -> None:
    entity = MessageEntity(type="text_mention", offset=5, length=7, user=NO_USERNAME)

    target, _ = await _target_and_rest(
        UserResolver(session), command("/ban Тихоня спам", entities=[entity]), "Тихоня спам"
    )

    assert target.id == NO_USERNAME.id
    assert target.source is TargetSource.MENTION


async def test_numeric_id_target(session) -> None:
    target, rest = await _target_and_rest(
        UserResolver(session), command("/ban 424242 2h спам"), "424242 2h спам"
    )

    assert target.id == 424242
    assert _split_duration(rest) == (timedelta(hours=2), "спам")
