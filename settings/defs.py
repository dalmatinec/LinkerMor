"""Реестр определений настроек (ТЗ §23).

Источник истины — код. В базе хранятся только переопределения конкретных
чатов, а значения по умолчанию живут здесь. Из этого следуют три вещи:

* добавление настройки не требует миграции базы;
* «сохранение после перезапуска» получается само собой: значение либо
  лежит в базе, либо берётся из определения;
* второго места с захардкоженным значением по умолчанию не существует.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.errors import SettingValidationError


@dataclass(frozen=True, slots=True)
class SettingDef:
    """Определение одной настройки чата.

    Attributes:
        key: Ключ вида ``модуль.имя``.
        default: Значение, пока чат его не переопределил.
        type: Тип значения: ``bool``, ``int`` или ``str``.
        module: Модуль-владелец. Панель группирует настройки по нему.
        description: Подпись в панели настроек.
        minimum, maximum: Границы для числовых значений.
        choices: Допустимые варианты для строковых значений.
    """

    key: str
    default: Any
    type: type
    module: str
    description: str
    minimum: int | None = None
    maximum: int | None = None
    choices: tuple[str, ...] = ()

    def coerce(self, value: Any) -> Any:
        """Проверить и привести значение к типу настройки.

        Raises:
            SettingValidationError: значение не подходит под определение.
        """
        if self.type is bool:
            return self._coerce_bool(value)
        if self.type is int:
            return self._coerce_int(value)
        return self._coerce_str(value)

    def _coerce_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in {"true", "false", "1", "0", "да", "нет"}:
            return value.lower() in {"true", "1", "да"}
        raise SettingValidationError(
            f"Настройка {self.key} принимает только включено или выключено",
            key=self.key,
            value=value,
        )

    def _coerce_int(self, value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise SettingValidationError(
                f"Настройка {self.key} принимает целое число", key=self.key, value=value
            )
        try:
            number = int(value)
        except ValueError as exc:
            raise SettingValidationError(
                f"Настройка {self.key} принимает целое число", key=self.key, value=value
            ) from exc

        if self.minimum is not None and number < self.minimum:
            raise SettingValidationError(
                f"Минимальное значение {self.key} — {self.minimum}", key=self.key, value=value
            )
        if self.maximum is not None and number > self.maximum:
            raise SettingValidationError(
                f"Максимальное значение {self.key} — {self.maximum}", key=self.key, value=value
            )
        return number

    def _coerce_str(self, value: Any) -> str:
        text = str(value)
        if self.choices and text not in self.choices:
            allowed = ", ".join(self.choices)
            raise SettingValidationError(
                f"Настройка {self.key} принимает одно из: {allowed}", key=self.key, value=value
            )
        return text


class SettingsRegistry:
    """Собранные определения настроек всех модулей."""

    def __init__(self, definitions: list[SettingDef]) -> None:
        self._defs: dict[str, SettingDef] = {}
        for definition in definitions:
            if definition.key in self._defs:
                raise SettingValidationError(
                    f"Настройка {definition.key} объявлена дважды", key=definition.key
                )
            self._defs[definition.key] = definition

    def get(self, key: str) -> SettingDef:
        try:
            return self._defs[key]
        except KeyError as exc:
            raise SettingValidationError(f"Неизвестная настройка {key}", key=key) from exc

    def has(self, key: str) -> bool:
        return key in self._defs

    def defaults(self) -> dict[str, Any]:
        """Значения по умолчанию для всех настроек."""
        return {key: definition.default for key, definition in self._defs.items()}

    def by_module(self, module: str) -> list[SettingDef]:
        return [d for d in self._defs.values() if d.module == module]

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(self._defs)

    def __len__(self) -> int:
        return len(self._defs)


#: Настройки, не принадлежащие ни одному модулю.
CORE_SETTINGS: list[SettingDef] = [
    SettingDef(
        key="core.language",
        default="ru",
        type=str,
        module="core",
        description="Язык сообщений бота в этом чате",
        choices=("ru",),
    ),
    SettingDef(
        key="core.delete_service_messages",
        default=False,
        type=bool,
        module="core",
        description="Удалять системные сообщения о входе и выходе участников",
    ),
    SettingDef(
        key="core.delete_commands",
        default=False,
        type=bool,
        module="core",
        description="Удалять команды администраторов после выполнения",
    ),
    SettingDef(
        key="core.staff_immune",
        default=True,
        type=bool,
        module="core",
        description="Не применять фильтры и ограничения к администрации чата",
    ),
]


def module_toggle_key(module: str) -> str:
    """Ключ настройки включения модуля в конкретном чате."""
    return f"modules.{module}.enabled"


def build_registry(module_specs: list) -> SettingsRegistry:
    """Собрать реестр из основных настроек и настроек модулей.

    Для каждого отключаемого модуля автоматически заводится переключатель:
    администратор чата может выключить ненужную функцию, не затрагивая
    другие чаты.
    """
    definitions = list(CORE_SETTINGS)
    for spec in module_specs:
        if spec.can_disable:
            definitions.append(
                SettingDef(
                    key=module_toggle_key(spec.name),
                    default=True,
                    type=bool,
                    module=spec.name,
                    description=f"Модуль «{spec.name}» включён в этом чате",
                )
            )
        definitions.extend(spec.setting_defs)
    return SettingsRegistry(definitions)
