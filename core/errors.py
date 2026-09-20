"""Иерархия ошибок приложения.

Правило проекта: пользователь Telegram никогда не видит traceback.
Любая ошибка, унаследованная от ``LinkerMorError``, несёт ключ текста
(``text_key``), который error-middleware превращает в понятное сообщение
через систему Custom Texts.
"""

from __future__ import annotations

from typing import Any


class LinkerMorError(Exception):
    """Базовая ошибка приложения, пригодная для показа пользователю."""

    #: Ключ в системе текстов. Подклассы переопределяют его.
    text_key: str = "error_unknown"

    def __init__(self, message: str = "", **context: Any) -> None:
        super().__init__(message or self.__class__.__name__)
        #: Значения для подстановки в текст ошибки.
        self.context: dict[str, Any] = context


class ConfigError(LinkerMorError):
    """Некорректная конфигурация. Поднимается на старте, до приёма апдейтов."""

    text_key = "error_config"


class PermissionDenied(LinkerMorError):
    """У пользователя нет права на действие в этом чате."""

    text_key = "permission_denied"


class BotMissingPermission(LinkerMorError):
    """Боту не хватает права Telegram для выполнения действия."""

    text_key = "bot_no_permission"

    def __init__(self, permission: str, **context: Any) -> None:
        super().__init__(f"bot lacks {permission}", permission=permission, **context)
        self.permission = permission


class TargetNotFound(LinkerMorError):
    """UserResolver не смог определить пользователя."""

    text_key = "user_not_found"


class ChatNotConnected(LinkerMorError):
    """Чат не подключён к боту или деактивирован."""

    text_key = "chat_not_connected"


class SettingValidationError(LinkerMorError):
    """Значение настройки не прошло валидацию."""

    text_key = "setting_invalid"


class ModuleRegistrationError(LinkerMorError):
    """Ошибка сборки реестра модулей. Всегда падает на старте."""

    text_key = "error_config"
