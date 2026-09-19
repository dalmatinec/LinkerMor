"""Проверка сообщений и управление списками (ТЗ §19)."""

from __future__ import annotations

from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from cache.backend import CacheBackend
from cache.keys import ChatEntity, chat_key
from core.constants import Role
from core.logging import get_logger
from guards.chat_type import InGroup
from guards.module_enabled import ModuleEnabled
from guards.role import HasRole
from mod_antispam.actions import apply_verdict
from mod_antispam.engine import FilterEngine, RuleContext
from mod_antispam.repo import ForwardRepository, WordRepository
from mod_antispam.rule_caps import CapsRule
from mod_antispam.rule_flood import FloodRule
from mod_antispam.rule_forwards import ForwardsRule, origin_of
from mod_antispam.rule_links import LinksRule
from mod_antispam.rule_media import MediaRule
from mod_antispam.rule_mentions import MentionsRule
from mod_antispam.rule_words import WordsRule
from mod_moderation.service import ModerationService
from permissions.service import PermissionService
from sender.sender import Sender
from settings.service import SettingsService
from texts.placeholders import chat_values, user_values
from texts.service import TextService

log = get_logger(__name__)

router = Router(name="antispam")

ADMIN_COMMAND = (InGroup(), ModuleEnabled("antispam"), HasRole(Role.CHAT_ADMIN))

#: Набор правил приложения. Новое правило — файл и строка здесь.
ENGINE = FilterEngine(
    [
        WordsRule(),
        ForwardsRule(),
        LinksRule(),
        FloodRule(),
        CapsRule(),
        MentionsRule(),
        MediaRule(),
    ]
)


async def _invalidate(cache: CacheBackend, chat_id: int, part: str) -> None:
    """Сбросить кеш списка этого чата."""
    await cache.delete(chat_key(ChatEntity.FILTER_RULES, chat_id, part))


async def _reply(
    message: Message, texts: TextService, sender: Sender, key: str,
    values: dict[str, Any] | None = None,
) -> None:
    payload = dict(values or {})
    payload.update(chat_values(message.chat))
    if message.from_user is not None:
        payload.update(user_values(message.from_user, prefix="admin"))
    await sender.reply(message, await texts.render(message.chat.id, key, payload))


@router.message(InGroup(), ModuleEnabled("antispam"), ~F.text.startswith("/"))
async def on_message(
    message: Message,
    session: AsyncSession,
    bot: Bot,
    cache: CacheBackend,
    settings: SettingsService,
    permissions: PermissionService,
    texts: TextService,
    sender: Sender,
    member: Any = None,
    is_anonymous_admin: bool = False,
) -> None:
    """Проверить сообщение по правилам чата."""
    user = message.from_user
    if user is None or user.is_bot:
        return

    # Администрация по умолчанию не подпадает под фильтры: иначе
    # модератор не смог бы процитировать нарушение при разборе.
    if await settings.get(message.chat.id, "core.staff_immune"):
        role = await permissions.role_of(
            message.chat.id, user.id, member=member, is_anonymous=is_anonymous_admin
        )
        if role >= Role.MODERATOR:
            return

    ctx = RuleContext(
        chat_id=message.chat.id,
        message=message,
        session=session,
        settings=settings,
        cache=cache,
    )
    verdict = await ENGINE.check(ctx)
    if verdict is None:
        return

    moderation = ModerationService(session, bot, permissions, settings)
    await apply_verdict(message, verdict, moderation, texts, sender)


# ─── Запрещённые слова ───────────────────────────────────────────────────────


@router.message(Command("addword"), *ADMIN_COMMAND)
async def cmd_add_word(
    message: Message, command: CommandObject, session: AsyncSession, cache: CacheBackend,
    texts: TextService, sender: Sender,
) -> None:
    """``/addword <слово>`` — запретить слово в этом чате."""
    word = (command.args or "").strip().lower()
    if not word:
        await _reply(message, texts, sender, "antispam_word_usage")
        return

    added = await WordRepository(session).add(message.chat.id, word, message.from_user.id)
    await _invalidate(cache, message.chat.id, "words")
    await _reply(
        message, texts, sender,
        "antispam_word_added" if added else "antispam_word_exists", {"reason": word},
    )


@router.message(Command("delword"), *ADMIN_COMMAND)
async def cmd_delete_word(
    message: Message, command: CommandObject, session: AsyncSession, cache: CacheBackend,
    texts: TextService, sender: Sender,
) -> None:
    """``/delword <слово>`` — убрать слово из списка."""
    word = (command.args or "").strip().lower()
    if not word:
        await _reply(message, texts, sender, "antispam_word_usage")
        return

    removed = await WordRepository(session).remove(message.chat.id, word)
    await _invalidate(cache, message.chat.id, "words")
    await _reply(
        message, texts, sender,
        "antispam_word_removed" if removed else "antispam_word_missing", {"reason": word},
    )


@router.message(Command("words"), *ADMIN_COMMAND)
async def cmd_words(
    message: Message, session: AsyncSession, texts: TextService, sender: Sender
) -> None:
    """``/words`` — список запрещённых слов."""
    words = await WordRepository(session).list_words(message.chat.id)
    if not words:
        await _reply(message, texts, sender, "antispam_words_empty")
        return

    await _reply(
        message, texts, sender, "antispam_words_list",
        {"items": ", ".join(sorted(words)), "count": str(len(words))},
    )


# ─── Белый список пересылок ──────────────────────────────────────────────────


@router.message(Command("allowforward"), *ADMIN_COMMAND)
async def cmd_allow_forward(
    message: Message, session: AsyncSession, cache: CacheBackend, texts: TextService,
    sender: Sender,
) -> None:
    """``/allowforward`` ответом на пересылку — разрешить её источник."""
    source = message.reply_to_message
    origin = origin_of(source) if source is not None else None

    if origin is None:
        await _reply(message, texts, sender, "antispam_forward_usage")
        return

    source_type, source_id, title = origin
    if not source_id:
        # Скрытый отправитель: идентификатора нет, разрешать нечего.
        await _reply(message, texts, sender, "antispam_forward_hidden")
        return

    added = await ForwardRepository(session).allow(
        message.chat.id, source_type, source_id, title, message.from_user.id
    )
    await _invalidate(cache, message.chat.id, "forwards")
    await _reply(
        message, texts, sender,
        "antispam_forward_allowed" if added else "antispam_forward_known",
        {"reason": title, "user": title},
    )


@router.message(Command("denyforward"), *ADMIN_COMMAND)
async def cmd_deny_forward(
    message: Message, session: AsyncSession, cache: CacheBackend, texts: TextService,
    sender: Sender,
) -> None:
    """``/denyforward`` ответом на пересылку — убрать источник из списка."""
    source = message.reply_to_message
    origin = origin_of(source) if source is not None else None

    if origin is None:
        await _reply(message, texts, sender, "antispam_forward_usage")
        return

    _, source_id, title = origin
    removed = await ForwardRepository(session).deny(message.chat.id, source_id)
    await _invalidate(cache, message.chat.id, "forwards")
    await _reply(
        message, texts, sender,
        "antispam_forward_denied" if removed else "antispam_forward_missing",
        {"reason": title, "user": title},
    )


@router.message(Command("forwards"), *ADMIN_COMMAND)
async def cmd_forwards(
    message: Message, session: AsyncSession, texts: TextService, sender: Sender
) -> None:
    """``/forwards`` — разрешённые источники пересылок."""
    sources = await ForwardRepository(session).list_all(message.chat.id)
    if not sources:
        await _reply(message, texts, sender, "antispam_forward_empty")
        return

    listing = "\n".join(f"• {item.title or item.source_id}" for item in sources)
    await _reply(
        message, texts, sender, "antispam_forward_list",
        {"items": listing, "count": str(len(sources))},
    )
