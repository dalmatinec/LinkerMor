"""Определение цели команды: reply, упоминание, username, ID (ТЗ §7)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aiogram.types import Chat as TgChat
from aiogram.types import Message, MessageEntity
from aiogram.types import User as TgUser

from core.errors import TargetNotFound
from resolver.user_resolver import TargetSource, UserResolver, split_argument
from tests.test_chat_repository import make_user

CHAT = TgChat(id=-1001111111111, type="supergroup", title="Чат")
ACTOR = TgUser(id=8243233601, is_bot=False, first_name="Админ", username="admin")
TARGET = TgUser(id=555, is_bot=False, first_name="Нарушитель", username="spammer")
NO_USERNAME = TgUser(id=777, is_bot=False, first_name="Без", last_name="Юзернейма")


def message(text: str = "/ban", *, reply_to: Message | None = None, entities=None) -> Message:
    return Message(
        message_id=10,
        date=datetime.now(UTC),
        chat=CHAT,
        from_user=ACTOR,
        text=text,
        entities=entities,
        reply_to_message=reply_to,
    )


def target_message(user: TgUser | None = None, sender_chat: TgChat | None = None) -> Message:
    return Message(
        message_id=5,
        date=datetime.now(UTC),
        chat=CHAT,
        from_user=user,
        sender_chat=sender_chat,
        text="сообщение нарушителя",
    )


# ─── Разбор аргументов ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("@user спам и флуд", ("@user", "спам и флуд")),
        ("123456 нарушение", ("123456", "нарушение")),
        ("@user", ("@user", "")),
        (None, (None, "")),
        ("   ", (None, "")),
    ],
)
def test_split_argument(text: str | None, expected: tuple) -> None:
    assert split_argument(text) == expected


# ─── Источники цели ──────────────────────────────────────────────────────────


async def test_reply_has_priority_over_argument(session) -> None:
    """Ответ на сообщение — самый частый способ: аргумент тогда причина."""
    await make_user(session, TARGET.id, "spammer")
    await make_user(session, 999, "other")

    resolved = await UserResolver(session).resolve(
        message(reply_to=target_message(TARGET)), argument="@other"
    )

    assert resolved.id == TARGET.id
    assert resolved.source is TargetSource.REPLY


async def test_resolve_by_username(session) -> None:
    await make_user(session, TARGET.id, "spammer")

    resolved = await UserResolver(session).resolve(message(), argument="@spammer")

    assert resolved.id == TARGET.id
    assert resolved.source is TargetSource.USERNAME


async def test_username_lookup_ignores_case(session) -> None:
    await make_user(session, TARGET.id, "SpAmMeR")

    resolved = await UserResolver(session).resolve_token("@spammer")

    assert resolved.id == TARGET.id


async def test_unknown_username_reports_clearly(session) -> None:
    """Метода «username → user_id» в Bot API нет: находим только знакомых."""
    with pytest.raises(TargetNotFound):
        await UserResolver(session).resolve_token("@никогда_не_писал")


async def test_resolve_by_numeric_id_even_if_unknown(session) -> None:
    """По ID можно забанить того, кого бот никогда не видел."""
    resolved = await UserResolver(session).resolve(message(), argument="424242")

    assert resolved.id == 424242
    assert resolved.source is TargetSource.USER_ID
    assert resolved.display_name == "424242"


async def test_known_id_gets_a_name(session) -> None:
    await make_user(session, TARGET.id, "spammer")

    resolved = await UserResolver(session).resolve_token(str(TARGET.id))

    assert resolved.username == "spammer"
    assert resolved.display_name != str(TARGET.id)


async def test_text_mention_resolves_user_without_username(session) -> None:
    """Единственный способ сослаться на человека без username."""
    entity = MessageEntity(type="text_mention", offset=5, length=3, user=NO_USERNAME)

    resolved = await UserResolver(session).resolve(message("/ban Без Юзернейма", entities=[entity]))

    assert resolved.id == NO_USERNAME.id
    assert resolved.source is TargetSource.MENTION
    assert resolved.username is None


async def test_reply_to_channel_post_targets_the_channel(session) -> None:
    """Пост от имени канала: обычный бан на него не действует."""
    channel = TgChat(id=-1005555555555, type="channel", title="Канал спамеров")

    resolved = await UserResolver(session).resolve(
        message(reply_to=target_message(sender_chat=channel))
    )

    assert resolved.is_chat is True
    assert resolved.id == channel.id
    assert resolved.source is TargetSource.SENDER_CHAT


async def test_missing_target_reports_clearly(session) -> None:
    with pytest.raises(TargetNotFound):
        await UserResolver(session).resolve(message())


async def test_mention_name_prefers_username(session) -> None:
    await make_user(session, TARGET.id, "spammer")
    resolved = await UserResolver(session).resolve_token("@spammer")

    assert resolved.mention_name == "@spammer"
