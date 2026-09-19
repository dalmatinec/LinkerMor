"""Реестр текстов.

Каждый текст, который видит пользователь, объявлен здесь и имеет ключ.
Строк, написанных прямо в хендлере, в проекте быть не должно — за этим
следит архитектурный тест.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.errors import LinkerMorError


@dataclass(frozen=True, slots=True)
class TextDef:
    """Определение текста.

    Attributes:
        key: Ключ, по которому текст запрашивается в коде.
        default: Значение по умолчанию на языке системы.
        module: Модуль-владелец: панель редактирования группирует по нему.
        description: Пояснение для администратора: когда текст показывается.
    """

    key: str
    default: str
    module: str
    description: str


class TextRegistry:
    """Собранные определения текстов всех модулей."""

    def __init__(self, definitions: list[TextDef]) -> None:
        self._defs: dict[str, TextDef] = {}
        for definition in definitions:
            if definition.key in self._defs:
                raise LinkerMorError(f"Текст {definition.key} объявлен дважды")
            self._defs[definition.key] = definition

    def get(self, key: str) -> TextDef:
        try:
            return self._defs[key]
        except KeyError as exc:
            raise LinkerMorError(f"Неизвестный текст {key}") from exc

    def has(self, key: str) -> bool:
        return key in self._defs

    def by_module(self, module: str) -> list[TextDef]:
        return [d for d in self._defs.values() if d.module == module]

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(self._defs)

    def __len__(self) -> int:
        return len(self._defs)


#: Тексты ядра: ошибки и служебные ответы, общие для всех модулей.
CORE_TEXTS: list[TextDef] = [
    TextDef(
        key="permission_denied",
        default="У вас нет прав для этого действия.",
        module="core",
        description="Пользователь попытался выполнить недоступное ему действие",
    ),
    TextDef(
        key="bot_no_permission",
        default="Боту не хватает права «{permission}». Выдайте его в настройках чата.",
        module="core",
        description="Боту не хватает права Telegram для выполнения действия",
    ),
    TextDef(
        key="user_not_found",
        default=(
            "Не удалось найти пользователя. Ответьте на его сообщение "
            "или укажите числовой ID — по @username находятся только те, "
            "кто уже писал в чате."
        ),
        module="core",
        description="UserResolver не смог определить, о ком идёт речь",
    ),
    TextDef(
        key="chat_not_connected",
        default="Этот чат ещё не подключён к боту.",
        module="core",
        description="Команда выполнена в чате, которого нет в базе",
    ),
    TextDef(
        key="setting_invalid",
        default="Значение не подходит: {reason}",
        module="core",
        description="Администратор ввёл недопустимое значение настройки",
    ),
    TextDef(
        key="error_unknown",
        default="Не удалось выполнить действие. Попробуйте позже.",
        module="core",
        description="Непредвиденная ошибка: подробности уходят в лог, не пользователю",
    ),
    TextDef(
        key="error_config",
        default="Бот настроен неверно. Сообщите владельцу.",
        module="core",
        description="Ошибка конфигурации приложения",
    ),
]


def build_registry(module_specs: list) -> TextRegistry:
    """Собрать реестр из текстов ядра и текстов модулей."""
    definitions = list(CORE_TEXTS)
    for spec in module_specs:
        definitions.extend(spec.text_defs)
    return TextRegistry(definitions)
