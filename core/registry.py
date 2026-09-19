"""Реестр модулей: каркас масштабирования проекта.

Каждый модуль (папка ``mod_*``) описывает себя одним объектом ``ModuleSpec``
в файле ``spec.py``. Реестр собирает спеки, проверяет их на конфликты и
подключает к диспетчеру в порядке ``priority``.

Добавление нового модуля — это создание папки и одна строка в списке
``ENABLED_MODULES``. Ядро при этом не меняется.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.errors import ModuleRegistrationError
from core.logging import get_logger

if TYPE_CHECKING:
    from aiogram import Dispatcher, Router

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ModuleSpec:
    """Паспорт модуля.

    Attributes:
        name: Уникальное имя. Используется как ключ настройки
            ``modules.<name>.enabled`` и в качестве префикса callback.
        priority: Позиция роутера в цепочке. Меньше — раньше. Порядок задан
            здесь явно, а не порядком импортов, поэтому его видно целиком.
        router: Роутер aiogram со всеми хендлерами модуля.
        setting_defs: Определения настроек для общего реестра.
        text_defs: Определения текстов для общего реестра.
        menu_items: Пункты динамической админ-панели.
        models: Классы моделей — нужны Alembic для autogenerate.
        requires_perms: Права бота, без которых модуль бесполезен.
        can_disable: Можно ли выключить модуль в отдельном чате.
    """

    name: str
    priority: int
    router: "Router"
    setting_defs: tuple[Any, ...] = ()
    text_defs: tuple[Any, ...] = ()
    menu_items: tuple[Any, ...] = ()
    models: tuple[type, ...] = ()
    requires_perms: tuple[str, ...] = ()
    can_disable: bool = True

    def __post_init__(self) -> None:
        if not self.name.isidentifier():
            raise ModuleRegistrationError(f"Имя модуля {self.name!r} не является идентификатором")


@dataclass(slots=True)
class ModuleRegistry:
    """Собранные модули приложения."""

    specs: list[ModuleSpec] = field(default_factory=list)

    def register(self, spec: ModuleSpec) -> None:
        """Добавить модуль, отвергая конфликты имён и приоритетов."""
        for existing in self.specs:
            if existing.name == spec.name:
                raise ModuleRegistrationError(f"Модуль {spec.name!r} зарегистрирован дважды")
            if existing.priority == spec.priority:
                raise ModuleRegistrationError(
                    f"Модули {existing.name!r} и {spec.name!r} имеют одинаковый "
                    f"priority={spec.priority}: порядок обработки был бы неопределённым"
                )
        self.specs.append(spec)

    def sorted_specs(self) -> list[ModuleSpec]:
        """Модули в порядке обработки апдейта."""
        return sorted(self.specs, key=lambda s: s.priority)

    def get(self, name: str) -> ModuleSpec:
        for spec in self.specs:
            if spec.name == name:
                return spec
        raise ModuleRegistrationError(f"Модуль {name!r} не зарегистрирован")

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(spec.name for spec in self.sorted_specs())

    @property
    def disableable(self) -> tuple[str, ...]:
        """Модули, которые администратор чата может выключить."""
        return tuple(s.name for s in self.sorted_specs() if s.can_disable)

    def all_models(self) -> tuple[type, ...]:
        """Все модели всех модулей — для Alembic autogenerate."""
        return tuple(model for spec in self.sorted_specs() for model in spec.models)

    def attach(self, dispatcher: "Dispatcher") -> None:
        """Подключить роутеры модулей к диспетчеру в порядке приоритета."""
        for spec in self.sorted_specs():
            dispatcher.include_router(spec.router)
            log.info(
                "модуль подключён",
                extra={"module": spec.name, "priority": spec.priority},
            )


def build_registry(specs: list[ModuleSpec]) -> ModuleRegistry:
    """Собрать реестр из списка спек, проверив конфликты."""
    registry = ModuleRegistry()
    for spec in specs:
        registry.register(spec)
    return registry
