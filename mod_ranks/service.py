"""Логика рангов (ТЗ §12).

Метрика выбирается для каждого чата: где-то ценится репутация, где-то
активность, где-то их сумма. Пороги редактируются, и изменение сразу
влияет на рантайм — ранги пересчитываются по свежим значениям, а не по
тем, что были при запуске.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from cache.backend import CacheBackend
from cache.keys import ChatEntity, chat_key
from core.logging import get_logger
from mod_ranks.models import Rank, RankMetric
from mod_ranks.repo import RankRepository
from mod_reputation.repo import ReputationRepository
from settings.service import SettingsService

log = get_logger(__name__)

RANKS_CACHE_TTL = 600


@dataclass(frozen=True, slots=True)
class RankSnapshot:
    """Ранг и соседние ступени для показа участнику."""

    current: Rank | None
    next_rank: Rank | None
    value: int

    @property
    def to_next(self) -> int:
        return max(0, self.next_rank.threshold - self.value) if self.next_rank else 0


@dataclass(frozen=True, slots=True)
class RankChange:
    """Переход между ступенями."""

    direction: str  # up | down
    old_name: str
    new_name: str
    value: int


class RankService:
    """Расчёт и обновление рангов."""

    def __init__(
        self,
        session: AsyncSession,
        cache: CacheBackend,
        settings: SettingsService,
    ) -> None:
        self._session = session
        self._cache = cache
        self._settings = settings
        self._repo = RankRepository(session)
        self._reputation = ReputationRepository(session)

    # ─── Ступени ─────────────────────────────────────────────────────────────

    async def ranks(self, chat_id: int) -> list[Rank]:
        """Ступени чата. Кешируются: читаются на каждом сообщении."""
        key = chat_key(ChatEntity.RANKS, chat_id)
        cached = await self._cache.get(key)
        if cached is not None:
            return cached

        ranks = await self._repo.list_ranks(chat_id)
        await self._cache.set(key, ranks, ttl=RANKS_CACHE_TTL)
        return ranks

    async def add(self, chat_id: int, name: str, threshold: int) -> Rank:
        rank = await self._repo.add(chat_id, name, threshold)
        await self.invalidate(chat_id)
        log.info("ранг добавлен", extra={"chat_id": chat_id, "rank": name,
                                         "threshold": threshold})
        return rank

    async def remove(self, chat_id: int, name: str) -> bool:
        removed = await self._repo.delete_by_name(chat_id, name)
        if removed:
            await self.invalidate(chat_id)
        return removed

    async def invalidate(self, chat_id: int) -> None:
        """Сбросить ступени этого чата: порог изменился."""
        await self._cache.delete(chat_key(ChatEntity.RANKS, chat_id))

    # ─── Расчёт ──────────────────────────────────────────────────────────────

    async def metric_value(self, chat_id: int, user_id: int, member: Any = None) -> int:
        """Значение показателя, по которому считается ранг в этом чате."""
        metric = str(await self._settings.get(chat_id, "ranks.metric"))

        if metric == RankMetric.MESSAGES:
            return int(getattr(member, "messages_total", 0) or 0)

        reputation = await self._reputation.value_of(chat_id, user_id)
        if metric == RankMetric.REPUTATION:
            return reputation

        return reputation + int(getattr(member, "messages_total", 0) or 0)

    @staticmethod
    def rank_for(ranks: list[Rank], value: int) -> Rank | None:
        """Наивысшая ступень, порог которой достигнут."""
        reached = [rank for rank in ranks if rank.threshold <= value]
        return max(reached, key=lambda rank: rank.threshold) if reached else None

    @staticmethod
    def next_after(ranks: list[Rank], value: int) -> Rank | None:
        ahead = [rank for rank in ranks if rank.threshold > value]
        return min(ahead, key=lambda rank: rank.threshold) if ahead else None

    async def snapshot(self, chat_id: int, user_id: int, member: Any = None) -> RankSnapshot:
        """Текущий ранг участника и расстояние до следующего."""
        value = await self.metric_value(chat_id, user_id, member)
        ranks = await self.ranks(chat_id)
        return RankSnapshot(
            current=self.rank_for(ranks, value),
            next_rank=self.next_after(ranks, value),
            value=value,
        )

    async def sync(self, chat_id: int, user_id: int, member: Any = None) -> RankChange | None:
        """Обновить ранг участника и сообщить о переходе.

        Возвращает ``None``, если ступень не изменилась. Хранение
        достигнутого ранга нужно именно для этого: иначе бот поздравлял бы
        при каждом сообщении.
        """
        ranks = await self.ranks(chat_id)
        if not ranks:
            return None

        value = await self.metric_value(chat_id, user_id, member)
        new_rank = self.rank_for(ranks, value)
        old_rank_id = await self._repo.user_rank_id(chat_id, user_id)
        new_rank_id = new_rank.id if new_rank else None

        if old_rank_id == new_rank_id:
            return None

        await self._repo.set_user_rank(chat_id, user_id, new_rank_id)

        old_name = next((r.name for r in ranks if r.id == old_rank_id), "")
        new_name = new_rank.name if new_rank else ""
        old_threshold = next((r.threshold for r in ranks if r.id == old_rank_id), -1)
        new_threshold = new_rank.threshold if new_rank else -1

        change = RankChange(
            direction="up" if new_threshold > old_threshold else "down",
            old_name=old_name,
            new_name=new_name,
            value=value,
        )
        log.info(
            "ранг изменён",
            extra={"chat_id": chat_id, "target_id": user_id, "direction": change.direction,
                   "rank": new_name or old_name, "value": value},
        )
        return change
