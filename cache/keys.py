"""Построение ключей кеша (ТЗ §22, критерий приёмки §32.7).

Главная идея: разделение сущностей на два непересекающихся набора.

* ``ChatEntity`` — данные конкретного чата. Ключ для них строится только
  функцией ``chat_key``, которая требует ``chat_id`` обязательным
  аргументом. Собрать ключ вида ``settings:welcome`` без чата технически
  невозможно: такой функции в проекте нет.
* ``GlobalEntity`` — общесистемные данные, у которых чата нет по смыслу.

Пересечение наборов запрещено и проверяется тестом.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

NAMESPACE: Final[str] = "lm"
SCHEMA_VERSION: Final[str] = "v1"


class ChatEntity(StrEnum):
    """Сущности, принадлежащие одному чату."""

    SETTINGS = "settings"
    TEXTS = "texts"
    TRIGGERS = "triggers"
    TRIGGER_COOLDOWN = "trigger_cd"
    ADMINS = "admins"
    BOT_PERMS = "bot_perms"
    RANKS = "ranks"
    FILTER_RULES = "filter_rules"
    FORWARD_WHITELIST = "forward_wl"
    KEYBOARDS = "keyboards"
    MODULES = "modules"


class GlobalEntity(StrEnum):
    """Сущности уровня системы, не привязанные к чату."""

    GLOBAL_TEXTS = "global_texts"
    SYSTEM_SETTINGS = "system_settings"
    USER_DIRECTORY = "user_directory"  # резолв username → user_id
    CALLBACK_TOKEN = "cb_token"
    BOT_INFO = "bot_info"


def chat_key(entity: ChatEntity, chat_id: int, *parts: str | int) -> str:
    """Ключ данных чата. ``chat_id`` обязателен и не имеет значения по умолчанию.

    >>> chat_key(ChatEntity.SETTINGS, -1001234567890)
    'lm:v1:settings:-1001234567890'
    >>> chat_key(ChatEntity.TEXTS, -100123, 'ru')
    'lm:v1:texts:-100123:ru'
    """
    if not isinstance(entity, ChatEntity):
        raise TypeError(f"{entity!r} не является сущностью чата: используйте global_key")
    tail = "".join(f":{part}" for part in parts)
    return f"{NAMESPACE}:{SCHEMA_VERSION}:{entity.value}:{chat_id}{tail}"


def global_key(entity: GlobalEntity, *parts: str | int) -> str:
    """Ключ общесистемных данных.

    >>> global_key(GlobalEntity.USER_DIRECTORY, 'durov')
    'lm:v1:user_directory:durov'
    """
    if not isinstance(entity, GlobalEntity):
        raise TypeError(
            f"{entity!r} — данные чата. Используйте chat_key и передайте chat_id явно."
        )
    tail = "".join(f":{part}" for part in parts)
    return f"{NAMESPACE}:{SCHEMA_VERSION}:{entity.value}{tail}"


def chat_prefix(chat_id: int) -> str:
    """Шаблон для сброса всего кеша одного чата.

    Применяется при отключении чата и при смене chat_id после миграции
    группы в супергруппу.
    """
    return f"{NAMESPACE}:{SCHEMA_VERSION}:*:{chat_id}*"
