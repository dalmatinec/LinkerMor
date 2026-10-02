"""Антифлуд для входящих сообщений пользователей.

Если пользователь пишет больше ``limit`` сообщений за ``window`` секунд,
бот перестаёт пересылать его сообщения в группу на ``mute`` секунд и один
раз предупреждает. Альбом (несколько фото одной отправкой) считается за
одно сообщение, иначе альбом из четырёх фото сам по себе был бы флудом.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum


class Verdict(Enum):
    OK = "ok"            # пропустить
    WARN = "warn"        # только что превысил: отклонить и предупредить
    MUTED = "muted"      # уже на паузе: отклонить молча


@dataclass
class _UserState:
    hits: deque[float] = field(default_factory=deque)
    muted_until: float = 0.0
    last_group: str | None = None


class FloodControl:
    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._users: dict[tuple[int, str], _UserState] = {}

    def check(
        self,
        user_id: int,
        limit: int,
        window: float,
        mute: float,
        media_group_id: str | None = None,
        kind: str = "msg",
    ) -> tuple[Verdict, int]:
        """Вердикт и сколько секунд осталось до конца паузы.

        ``kind`` разделяет счётчики: нажатия /start не съедают лимит
        обычных сообщений, но и сами ограничены.
        """
        now = self._clock()
        state = self._users.setdefault((user_id, kind), _UserState())

        if now < state.muted_until:
            return Verdict.MUTED, int(state.muted_until - now) + 1

        if media_group_id is not None and media_group_id == state.last_group:
            return Verdict.OK, 0
        state.last_group = media_group_id

        while state.hits and now - state.hits[0] >= window:
            state.hits.popleft()
        if len(state.hits) >= limit:
            state.hits.clear()
            state.muted_until = now + mute
            return Verdict.WARN, int(mute)
        state.hits.append(now)

        if len(self._users) > 20000:
            self._prune(now, window)
        return Verdict.OK, 0

    def _prune(self, now: float, window: float) -> None:
        for key, st in list(self._users.items()):
            if now >= st.muted_until and (not st.hits or now - st.hits[-1] > window):
                del self._users[key]
