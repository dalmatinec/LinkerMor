"""Логика репутации (ТЗ §11).

Ограничения существуют не ради строгости: без них репутация превращается
в игру двух человек, которые благодарят друг друга по кругу.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from mod_reputation.repo import ReputationRepository
from resolver.duration import format_duration
from settings.service import SettingsService

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ReputationResult:
    """Что произошло и что сказать."""

    text_key: str
    values: dict[str, Any] = field(default_factory=dict)
    applied: bool = False
    value_after: int = 0


class ReputationService:
    """Изменение и показ репутации."""

    def __init__(self, session: AsyncSession, settings: SettingsService) -> None:
        self._session = session
        self._settings = settings
        self._repo = ReputationRepository(session)

    async def change(
        self,
        chat_id: int,
        actor_id: int,
        target_id: int,
        delta: int,
        *,
        reason: str | None = None,
        target_name: str = "",
        enforce_limits: bool = True,
    ) -> ReputationResult:
        """Изменить репутацию участника.

        Args:
            enforce_limits: Проверять запреты. Администратор, меняющий
                репутацию командой, от них освобождён.
        """
        values: dict[str, Any] = {"user": target_name, "delta": str(delta)}

        if delta < 0 and not await self._settings.get(chat_id, "reputation.allow_minus"):
            return ReputationResult("reputation_minus_disabled", values)

        if enforce_limits:
            if actor_id == target_id:
                return ReputationResult("reputation_self", values)

            refusal = await self._check_limits(chat_id, actor_id, target_id, values)
            if refusal is not None:
                return refusal

        value_after = await self._repo.apply(chat_id, target_id, delta)
        await self._repo.record(
            chat_id=chat_id,
            user_id=target_id,
            actor_id=actor_id,
            delta=delta,
            value_after=value_after,
            reason=reason,
        )

        values["reputation"] = str(value_after)
        log.info(
            "репутация изменена",
            extra={"chat_id": chat_id, "target_id": target_id, "actor": actor_id,
                   "delta": delta, "value": value_after},
        )
        return ReputationResult(
            "reputation_given" if delta > 0 else "reputation_taken",
            values,
            applied=True,
            value_after=value_after,
        )

    async def _check_limits(
        self, chat_id: int, actor_id: int, target_id: int, values: dict[str, Any]
    ) -> ReputationResult | None:
        """Проверить паузу между изменениями и дневной предел."""
        cooldown = int(await self._settings.get(chat_id, "reputation.cooldown"))
        if cooldown:
            elapsed = await self._repo.seconds_since_last(chat_id, actor_id, target_id)
            if elapsed is not None and elapsed < cooldown:
                from datetime import timedelta

                values["duration"] = format_duration(timedelta(seconds=cooldown - elapsed))
                return ReputationResult("reputation_cooldown", values)

        limit = int(await self._settings.get(chat_id, "reputation.daily_limit"))
        if limit and await self._repo.given_last_day(chat_id, actor_id) >= limit:
            values["count"] = str(limit)
            return ReputationResult("reputation_limit", values)

        return None

    async def show(self, chat_id: int, user_id: int, name: str) -> ReputationResult:
        """Показать репутацию и место участника."""
        value = await self._repo.value_of(chat_id, user_id)
        position = await self._repo.position_of(chat_id, user_id)
        return ReputationResult(
            "reputation_show",
            {"user": name, "reputation": str(value), "position": str(position)},
            value_after=value,
        )

    async def top(self, chat_id: int, limit: int = 10) -> list[tuple[int, int]]:
        return await self._repo.top(chat_id, limit)

    async def value_of(self, chat_id: int, user_id: int) -> int:
        return await self._repo.value_of(chat_id, user_id)
