"""Движок фильтров (ТЗ §19).

Правила устроены одинаково: у каждого есть включённость, действие и срок,
настраиваемые для каждого чата. Проверки идут по порядку приоритета, и
первое сработавшее останавливает конвейер — иначе одно сообщение вызвало
бы несколько наказаний подряд.

Добавление правила — это новый файл ``rule_*.py`` и одна строка в списке
``RULES``. Ядро движка при этом не меняется.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from cache.backend import CacheBackend
from core.constants import ActionType
from core.logging import get_logger
from settings.service import SettingsService

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RuleContext:
    """Всё, что нужно правилу для проверки одного сообщения."""

    chat_id: int
    message: Message
    session: AsyncSession
    settings: SettingsService
    cache: CacheBackend

    @property
    def text(self) -> str:
        return self.message.text or self.message.caption or ""

    @property
    def user_id(self) -> int:
        user = self.message.from_user
        return user.id if user is not None else 0


@dataclass(frozen=True, slots=True)
class RuleVerdict:
    """Решение сработавшего правила."""

    rule: str
    action: ActionType
    delete: bool
    duration: timedelta | None = None
    #: Ключ текста для сообщения нарушителю.
    text_key: str = ""
    values: dict[str, Any] = field(default_factory=dict)


class Rule:
    """Базовое правило.

    Подклассу достаточно задать имя, приоритет и реализовать ``detect``.
    Чтение настроек и сборка решения одинаковы для всех правил.
    """

    name: str = ""
    priority: int = 100
    #: Ключ текста, который увидит нарушитель.
    text_key: str = ""
    #: Действие по умолчанию, если чат его не переопределил.
    default_action: str = ActionType.DELETE

    async def detect(self, ctx: RuleContext) -> dict[str, Any] | None:
        """Проверить сообщение.

        Returns:
            Значения для подстановки в текст, если правило сработало,
            иначе ``None``.
        """
        raise NotImplementedError

    async def is_enabled(self, ctx: RuleContext) -> bool:
        return bool(await ctx.settings.get(ctx.chat_id, f"antispam.{self.name}.enabled"))

    async def build_verdict(self, ctx: RuleContext, values: dict[str, Any]) -> RuleVerdict:
        action = str(await ctx.settings.get(ctx.chat_id, f"antispam.{self.name}.action"))
        seconds = int(await ctx.settings.get(ctx.chat_id, f"antispam.{self.name}.duration"))

        return RuleVerdict(
            rule=self.name,
            action=ActionType(action),
            delete=bool(await ctx.settings.get(ctx.chat_id, f"antispam.{self.name}.delete")),
            duration=timedelta(seconds=seconds) if seconds else None,
            text_key=self.text_key,
            values=values,
        )


class FilterEngine:
    """Прогоняет сообщение по правилам чата."""

    def __init__(self, rules: list[Rule]) -> None:
        self._rules = sorted(rules, key=lambda rule: rule.priority)

    @property
    def rules(self) -> list[Rule]:
        return list(self._rules)

    async def check(self, ctx: RuleContext) -> RuleVerdict | None:
        """Первое сработавшее правило останавливает проверку.

        Останов важен: без него сообщение с ссылкой и капсом получило бы
        два наказания за одно нарушение.
        """
        for rule in self._rules:
            if not await rule.is_enabled(ctx):
                continue

            values = await rule.detect(ctx)
            if values is None:
                continue

            verdict = await rule.build_verdict(ctx, values)
            log.info(
                "сработало правило антиспама",
                extra={"chat_id": ctx.chat_id, "target_id": ctx.user_id,
                       "rule": rule.name, "action": verdict.action},
            )
            return verdict

        return None
