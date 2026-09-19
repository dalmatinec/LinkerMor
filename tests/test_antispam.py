"""Антиспам: правила, движок и белый список пересылок (ТЗ §19)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from aiogram.types import Chat as TgChat
from aiogram.types import (
    Message,
    MessageEntity,
    MessageOriginChannel,
    MessageOriginHiddenUser,
    MessageOriginUser,
    PhotoSize,
)
from aiogram.types import User as TgUser

from cache.memory import MemoryCache
from core.constants import ActionType
from mod_antispam.engine import FilterEngine, RuleContext
from mod_antispam.models import ForwardSource
from mod_antispam.repo import ForwardRepository, WordRepository
from mod_antispam.rule_caps import CapsRule
from mod_antispam.rule_flood import FloodRule
from mod_antispam.rule_forwards import ForwardsRule
from mod_antispam.rule_links import LinksRule
from mod_antispam.rule_media import MediaRule
from mod_antispam.rule_mentions import MentionsRule
from mod_antispam.rule_words import WordsRule
from settings.defs import build_registry as build_settings
from settings.service import SettingsService
from tests.test_chat_repository import make_chat, make_user

CHAT_A = -1001111111111
CHAT_B = -1002222222222
ADMIN_ID = 8243233601
USER = TgUser(id=555, is_bot=False, first_name="Участник", username="member")
TG_CHAT = TgChat(id=CHAT_A, type="supergroup", title="Чат")
SPAM_CHANNEL = TgChat(id=-1009999999999, type="channel", title="Спам-канал")


def specs() -> list:
    from core.bootstrap import ENABLED_MODULES

    return ENABLED_MODULES()


@pytest.fixture
def cache() -> MemoryCache:
    return MemoryCache()


@pytest.fixture
def settings(session, cache) -> SettingsService:
    return SettingsService(session, cache, build_settings(specs()))


def message(
    text: str = "обычное сообщение",
    *,
    entities=None,
    chat_id: int = CHAT_A,
    forward_origin=None,
    automatic: bool = False,
    photo: bool = False,
) -> Message:
    return Message(
        message_id=10,
        date=datetime.now(UTC),
        chat=TgChat(id=chat_id, type="supergroup", title="Чат"),
        from_user=USER,
        text=None if photo else text,
        caption=text if photo else None,
        entities=None if photo else entities,
        caption_entities=entities if photo else None,
        forward_origin=forward_origin,
        is_automatic_forward=automatic or None,
        photo=[PhotoSize(file_id="f", file_unique_id="u", width=10, height=10)]
        if photo
        else None,
    )


def context(session, settings, cache, msg: Message) -> RuleContext:
    return RuleContext(
        chat_id=msg.chat.id, message=msg, session=session, settings=settings, cache=cache
    )


async def setup(session, settings: SettingsService, chat_id: int = CHAT_A) -> None:
    await make_chat(session, chat_id)
    await make_user(session, USER.id, "member")
    await make_user(session, ADMIN_ID, "admin")


# ─── Запрещённые слова ───────────────────────────────────────────────────────


async def test_word_rule_detects_listed_word(session, settings, cache) -> None:
    await setup(session, settings)
    await WordRepository(session).add(CHAT_A, "реклама", ADMIN_ID)

    result = await WordsRule().detect(
        context(session, settings, cache, message("тут была реклама"))
    )

    assert result == {"reason": "реклама"}


async def test_word_rule_respects_word_boundaries(session, settings, cache) -> None:
    """«рак» не должен срабатывать внутри «ракета»."""
    await setup(session, settings)
    await WordRepository(session).add(CHAT_A, "рак", ADMIN_ID)

    result = await WordsRule().detect(
        context(session, settings, cache, message("запустили ракету"))
    )

    assert result is None


async def test_word_rule_substring_mode(session, settings, cache) -> None:
    await setup(session, settings)
    await settings.set(CHAT_A, "antispam.words.whole_only", False, ADMIN_ID)
    await WordRepository(session).add(CHAT_A, "рак", ADMIN_ID)

    result = await WordsRule().detect(
        context(session, settings, cache, message("запустили ракету"))
    )

    assert result is not None


async def test_word_lists_are_per_chat(session, settings, cache) -> None:
    await setup(session, settings, CHAT_A)
    await setup(session, settings, CHAT_B)
    await WordRepository(session).add(CHAT_A, "реклама", ADMIN_ID)

    in_a = await WordsRule().detect(
        context(session, settings, cache, message("реклама", chat_id=CHAT_A))
    )
    in_b = await WordsRule().detect(
        context(session, settings, cache, message("реклама", chat_id=CHAT_B))
    )

    assert in_a is not None
    assert in_b is None


# ─── Ссылки ──────────────────────────────────────────────────────────────────


async def test_link_rule_uses_telegram_markup(session, settings, cache) -> None:
    """Ссылки берутся из разметки: обойти пробелами не получится."""
    await setup(session, settings)
    entity = MessageEntity(type="url", offset=0, length=17)

    result = await LinksRule().detect(
        context(session, settings, cache, message("https://t.me/spam", entities=[entity]))
    )

    assert result is not None


async def test_link_rule_can_allow_non_telegram(session, settings, cache) -> None:
    await setup(session, settings)
    entity = MessageEntity(type="url", offset=0, length=19)

    result = await LinksRule().detect(
        context(session, settings, cache, message("https://example.org", entities=[entity]))
    )

    assert result is None  # по умолчанию запрещены только ссылки на Telegram


async def test_link_rule_blocks_any_link_when_configured(session, settings, cache) -> None:
    await setup(session, settings)
    await settings.set(CHAT_A, "antispam.links.telegram_only", False, ADMIN_ID)
    entity = MessageEntity(type="url", offset=0, length=19)

    result = await LinksRule().detect(
        context(session, settings, cache, message("https://example.org", entities=[entity]))
    )

    assert result is not None


# ─── Флуд ────────────────────────────────────────────────────────────────────


async def test_flood_rule_triggers_over_limit(session, settings, cache) -> None:
    await setup(session, settings)
    await settings.set(CHAT_A, "antispam.flood.limit", 3, ADMIN_ID)
    rule = FloodRule()
    ctx = context(session, settings, cache, message())

    verdicts = [await rule.detect(ctx) for _ in range(4)]

    assert verdicts[:3] == [None, None, None]
    assert verdicts[3] is not None


async def test_flood_counters_are_per_user_and_chat(session, settings, cache) -> None:
    await setup(session, settings, CHAT_A)
    await setup(session, settings, CHAT_B)
    await settings.set(CHAT_A, "antispam.flood.limit", 2, ADMIN_ID)
    await settings.set(CHAT_B, "antispam.flood.limit", 2, ADMIN_ID)
    rule = FloodRule()

    for _ in range(3):
        await rule.detect(context(session, settings, cache, message(chat_id=CHAT_A)))

    assert await rule.detect(context(session, settings, cache, message(chat_id=CHAT_B))) is None


# ─── Капс ────────────────────────────────────────────────────────────────────


async def test_caps_rule_triggers(session, settings, cache) -> None:
    await setup(session, settings)

    result = await CapsRule().detect(
        context(session, settings, cache, message("КУПИТЕ СРОЧНО ТОВАР"))
    )

    assert result is not None


async def test_caps_rule_ignores_short_messages(session, settings, cache) -> None:
    """«ОК» капсом не является проблемой."""
    await setup(session, settings)

    result = await CapsRule().detect(context(session, settings, cache, message("ОК")))

    assert result is None


async def test_caps_rule_ignores_normal_text(session, settings, cache) -> None:
    await setup(session, settings)

    result = await CapsRule().detect(
        context(session, settings, cache, message("Обычное сообщение без капса"))
    )

    assert result is None


# ─── Упоминания ──────────────────────────────────────────────────────────────


async def test_mentions_rule_triggers_over_limit(session, settings, cache) -> None:
    await setup(session, settings)
    entities = [MessageEntity(type="mention", offset=i * 5, length=4) for i in range(6)]

    result = await MentionsRule().detect(
        context(session, settings, cache, message("@a @b @c @d @e @f", entities=entities))
    )

    assert result == {"count": "6"}


async def test_mentions_rule_allows_few(session, settings, cache) -> None:
    await setup(session, settings)
    entities = [MessageEntity(type="mention", offset=0, length=4)]

    result = await MentionsRule().detect(
        context(session, settings, cache, message("@a", entities=entities))
    )

    assert result is None


# ─── Вложения ────────────────────────────────────────────────────────────────


async def test_media_rule_respects_configured_types(session, settings, cache) -> None:
    await setup(session, settings)
    await settings.set(CHAT_A, "antispam.media.types", "photo,sticker", ADMIN_ID)

    result = await MediaRule().detect(
        context(session, settings, cache, message("подпись", photo=True))
    )

    assert result == {"reason": "photo"}


async def test_media_rule_silent_when_nothing_forbidden(session, settings, cache) -> None:
    await setup(session, settings)

    result = await MediaRule().detect(
        context(session, settings, cache, message("подпись", photo=True))
    )

    assert result is None


# ─── Пересылки ───────────────────────────────────────────────────────────────


def channel_forward() -> Message:
    origin = MessageOriginChannel(
        type="channel", date=datetime.now(UTC), chat=SPAM_CHANNEL, message_id=5
    )
    return message("пересланный текст", forward_origin=origin)


async def test_forward_from_unknown_source_is_blocked(session, settings, cache) -> None:
    await setup(session, settings)

    result = await ForwardsRule().detect(context(session, settings, cache, channel_forward()))

    assert result is not None
    assert result["reason"] == "Спам-канал"


async def test_whitelisted_source_passes(session, settings, cache) -> None:
    await setup(session, settings)
    await ForwardRepository(session).allow(
        CHAT_A, ForwardSource.CHANNEL, SPAM_CHANNEL.id, "Спам-канал", ADMIN_ID
    )

    result = await ForwardsRule().detect(context(session, settings, cache, channel_forward()))

    assert result is None


async def test_automatic_forward_from_linked_channel_passes(session, settings, cache) -> None:
    """Посты привязанного канала пересылает сам Telegram — это не спам."""
    await setup(session, settings)
    origin = MessageOriginChannel(
        type="channel", date=datetime.now(UTC), chat=SPAM_CHANNEL, message_id=5
    )
    msg = message("пост канала", forward_origin=origin, automatic=True)

    result = await ForwardsRule().detect(context(session, settings, cache, msg))

    assert result is None


async def test_hidden_sender_cannot_be_whitelisted(session, settings, cache) -> None:
    """У скрытого отправителя нет идентификатора: разрешать нечего."""
    await setup(session, settings)
    origin = MessageOriginHiddenUser(
        type="hidden_user", date=datetime.now(UTC), sender_user_name="Аноним"
    )

    result = await ForwardsRule().detect(
        context(session, settings, cache, message("текст", forward_origin=origin))
    )

    assert result is not None


async def test_forward_from_user_is_recognised(session, settings, cache) -> None:
    await setup(session, settings)
    origin = MessageOriginUser(type="user", date=datetime.now(UTC), sender_user=USER)

    result = await ForwardsRule().detect(
        context(session, settings, cache, message("текст", forward_origin=origin))
    )

    assert result is not None


async def test_ordinary_message_is_not_a_forward(session, settings, cache) -> None:
    await setup(session, settings)

    result = await ForwardsRule().detect(context(session, settings, cache, message()))

    assert result is None


async def test_whitelist_is_per_chat(session, settings, cache) -> None:
    await setup(session, settings, CHAT_A)
    await setup(session, settings, CHAT_B)
    await ForwardRepository(session).allow(
        CHAT_A, ForwardSource.CHANNEL, SPAM_CHANNEL.id, "Спам-канал", ADMIN_ID
    )

    origin = MessageOriginChannel(
        type="channel", date=datetime.now(UTC), chat=SPAM_CHANNEL, message_id=5
    )
    in_a = await ForwardsRule().detect(
        context(session, settings, cache, message("т", forward_origin=origin, chat_id=CHAT_A))
    )
    in_b = await ForwardsRule().detect(
        context(session, settings, cache, message("т", forward_origin=origin, chat_id=CHAT_B))
    )

    assert in_a is None
    assert in_b is not None


# ─── Движок ──────────────────────────────────────────────────────────────────


async def test_disabled_rules_are_skipped(session, settings, cache) -> None:
    """По умолчанию правила выключены: бот не наказывает сразу после входа."""
    await setup(session, settings)
    await WordRepository(session).add(CHAT_A, "реклама", ADMIN_ID)
    engine = FilterEngine([WordsRule()])

    verdict = await engine.check(context(session, settings, cache, message("реклама")))

    assert verdict is None


async def test_enabled_rule_produces_verdict(session, settings, cache) -> None:
    await setup(session, settings)
    await settings.set(CHAT_A, "antispam.words.enabled", True, ADMIN_ID)
    await settings.set(CHAT_A, "antispam.words.action", "mute", ADMIN_ID)
    await settings.set(CHAT_A, "antispam.words.duration", 600, ADMIN_ID)
    await WordRepository(session).add(CHAT_A, "реклама", ADMIN_ID)

    verdict = await FilterEngine([WordsRule()]).check(
        context(session, settings, cache, message("реклама"))
    )

    assert verdict is not None
    assert verdict.rule == "words"
    assert verdict.action is ActionType.MUTE
    assert verdict.duration.total_seconds() == 600
    assert verdict.delete is True


async def test_first_matching_rule_stops_the_pipeline(session, settings, cache) -> None:
    """Иначе сообщение со ссылкой и капсом получило бы два наказания."""
    await setup(session, settings)
    for rule in ("links", "caps"):
        await settings.set(CHAT_A, f"antispam.{rule}.enabled", True, ADMIN_ID)
    await settings.set(CHAT_A, "antispam.links.telegram_only", False, ADMIN_ID)

    entity = MessageEntity(type="url", offset=0, length=19)
    msg = message("HTTPS://EXAMPLE.ORG СРОЧНО КУПИТЕ", entities=[entity])
    engine = FilterEngine([LinksRule(), CapsRule()])

    verdict = await engine.check(context(session, settings, cache, msg))

    assert verdict is not None
    assert verdict.rule == "links"  # ссылки идут раньше капса по приоритету


async def test_rules_run_in_priority_order() -> None:
    engine = FilterEngine([MediaRule(), WordsRule(), FloodRule(), ForwardsRule()])

    assert [rule.name for rule in engine.rules] == ["words", "forwards", "flood", "media"]


async def test_settings_are_per_chat(session, settings, cache) -> None:
    await setup(session, settings, CHAT_A)
    await setup(session, settings, CHAT_B)
    await settings.set(CHAT_A, "antispam.caps.enabled", True, ADMIN_ID)
    engine = FilterEngine([CapsRule()])

    in_a = await engine.check(
        context(session, settings, cache, message("СРОЧНО КУПИТЕ ТОВАР", chat_id=CHAT_A))
    )
    in_b = await engine.check(
        context(session, settings, cache, message("СРОЧНО КУПИТЕ ТОВАР", chat_id=CHAT_B))
    )

    assert in_a is not None
    assert in_b is None
