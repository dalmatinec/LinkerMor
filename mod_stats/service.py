"""Сводка по чату.

Сервис отдаёт числа, а оформление задаётся текстом в панели: владелец
переставляет строки, добавляет премиум-эмодзи и меняет формулировки, не
трогая код. Поэтому здесь нет ни одной готовой фразы — только значения.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from mod_chats.repo import UserRepository
from mod_stats.repo import StatsRepository

#: Символы для столбиков графика — от самого низкого к самому высокому.
BARS = "▁▂▃▄▅▆▇█"

DAY_NAMES = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


def sparkline(values: list[int]) -> str:
    """Собрать компактный график из блочных символов.

    Картинку рисовать незачем: строка отображается одинаково на всех
    устройствах, не требует загрузки и занимает одну строку сообщения.
    """
    if not values:
        return ""

    peak = max(values)
    if peak == 0:
        return BARS[0] * len(values)

    return "".join(BARS[min(len(BARS) - 1, value * (len(BARS) - 1) // peak)] for value in values)


@dataclass(frozen=True, slots=True)
class ChatStats:
    """Собранные показатели чата."""

    values: dict[str, Any]


class StatsService:
    """Собирает показатели чата за разные периоды."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = StatsRepository(session)
        self._users = UserRepository(session)

    async def register_message(self, chat_id: int, user_id: int) -> None:
        await self._repo.register_message(chat_id, user_id)

    async def collect(self, chat_id: int, chat_title: str = "") -> ChatStats:
        """Собрать сводку по чату."""
        now = datetime.now(UTC)
        today = now.date()
        week_ago = today - timedelta(days=6)
        month_ago = today - timedelta(days=29)

        punishments = await self._repo.punishments_since(chat_id, now - timedelta(days=7))
        series = await self._repo.daily_series(chat_id, days=7)

        top_lines = []
        for position, (user_id, count) in enumerate(
            await self._repo.top_members(chat_id, week_ago), start=1
        ):
            stored = await self._users.get(user_id)
            name = stored.full_name if stored is not None else str(user_id)
            top_lines.append(f"{position}. {name} — {count}")

        values: dict[str, Any] = {
            "chat_title": chat_title,
            "chat": chat_title,
            # Сообщения
            "messages_today": str(await self._repo.messages_since(chat_id, today)),
            "messages_week": str(await self._repo.messages_since(chat_id, week_ago)),
            "messages_month": str(await self._repo.messages_since(chat_id, month_ago)),
            # Участники
            "active_today": str(await self._repo.active_members_since(chat_id, today)),
            "active_week": str(await self._repo.active_members_since(chat_id, week_ago)),
            "members_total": str(await self._repo.members_total(chat_id)),
            "staff_total": str(await self._repo.staff_total(chat_id)),
            "new_week": str(
                await self._repo.new_members_since(chat_id, now - timedelta(days=7))
            ),
            # Модерация
            "bans": str(punishments.get("ban", 0)),
            "mutes": str(punishments.get("mute", 0)),
            "kicks": str(punishments.get("kick", 0)),
            "warns_week": str(
                await self._repo.warnings_since(chat_id, now - timedelta(days=7))
            ),
            "filter_actions": str(
                await self._repo.filter_punishments_since(chat_id, now - timedelta(days=7))
            ),
            # Наглядное
            "chart": sparkline([count for _, count in series]),
            "days": " ".join(DAY_NAMES[day.weekday()] for day, _ in series),
            "items": "\n".join(top_lines),
        }
        return ChatStats(values=values)
