"""Общие перечисления и константы проекта.

Здесь живут только значения, которые нужны нескольким модулям сразу.
Всё, что нужно одному модулю, объявляется внутри его папки.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import Final

# ─── Роли ────────────────────────────────────────────────────────────────────


class Role(IntEnum):
    """Роль пользователя В КОНКРЕТНОМ чате.

    Числовые значения позволяют сравнивать роли через ``>=``.
    BOT_OWNER — единственная глобальная роль, остальные всегда привязаны
    к паре (chat_id, user_id): один и тот же человек может быть
    администратором в одном чате и обычным участником в другом.
    """

    MEMBER = 10
    MODERATOR = 40  # роль уровня бота, не администратор Telegram
    CHAT_ADMIN = 60  # администратор чата в Telegram
    CHAT_OWNER = 80  # создатель чата
    BOT_OWNER = 100  # владелец бота, OWNER_IDS


# ─── Действия модерации ──────────────────────────────────────────────────────


class ActionType(StrEnum):
    """Что бот делает с нарушителем. Используется фильтрами и капчей."""

    NONE = "none"
    DELETE = "delete"
    WARN = "warn"
    MUTE = "mute"
    KICK = "kick"  # ban + немедленный unban: пользователь может вернуться
    BAN = "ban"


class FilterVerdict(StrEnum):
    """Результат работы правила фильтра для конвейера обработки."""

    ALLOW = "allow"  # правило не сработало, проверяем следующее
    STOP = "stop"  # правило сработало, конвейер останавливается


# ─── Права бота в чате ───────────────────────────────────────────────────────


class BotPermission(StrEnum):
    """Права бота, которые нужно проверять перед вызовом методов API."""

    DELETE_MESSAGES = "can_delete_messages"
    RESTRICT_MEMBERS = "can_restrict_members"
    INVITE_USERS = "can_invite_users"
    PIN_MESSAGES = "can_pin_messages"
    MANAGE_CHAT = "can_manage_chat"
    PROMOTE_MEMBERS = "can_promote_members"


# ─── Лимиты Telegram и приложения ────────────────────────────────────────────

CALLBACK_DATA_MAX_BYTES: Final[int] = 64
MESSAGE_TEXT_MAX_LENGTH: Final[int] = 4096
CAPTION_MAX_LENGTH: Final[int] = 1024
BUTTON_TEXT_MAX_LENGTH: Final[int] = 64

#: Мут короче 30 секунд или длиннее 366 дней Telegram трактует как вечный.
MIN_RESTRICT_SECONDS: Final[int] = 30
MAX_RESTRICT_SECONDS: Final[int] = 366 * 24 * 60 * 60

#: Служебный бот, от имени которого приходят сообщения анонимных админов.
ANONYMOUS_ADMIN_BOT_ID: Final[int] = 1087968824  # @GroupAnonymousBot

DEFAULT_LANGUAGE: Final[str] = "ru"
