"""Капча при /start: пример на сложение и четыре кнопки с ответами."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

MAX_ATTEMPTS = 3
LOCK_SECONDS = 60
TTL_SECONDS = 600


@dataclass
class Challenge:
    question: str
    answer: int
    options: list[int]
    attempts: int = 0
    created: float = 0.0


def generate(rng: random.Random | None = None) -> Challenge:
    rng = rng or random.Random()
    a, b = rng.randint(1, 9), rng.randint(1, 9)
    answer = a + b
    options = {answer}
    while len(options) < 4:
        options.add(max(0, answer + rng.choice([-3, -2, -1, 1, 2, 3, 4])))
    shuffled = list(options)
    rng.shuffle(shuffled)
    return Challenge(f"{a} + {b} = ?", answer, shuffled, created=time.monotonic())


class CaptchaStore:
    """Активные капчи в памяти. После перезапуска пользователь просто
    получает новую, проходить её заново не обидно."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._items: dict[int, Challenge] = {}
        self._locked: dict[int, float] = {}

    def locked_for(self, user_id: int) -> int:
        until = self._locked.get(user_id, 0.0)
        left = until - self._clock()
        if left <= 0:
            self._locked.pop(user_id, None)
            return 0
        return int(left) + 1

    def new(self, user_id: int, attempts: int = 0) -> Challenge:
        if len(self._items) > 10000:
            self._prune()
        ch = generate()
        ch.attempts = attempts
        ch.created = self._clock()
        self._items[user_id] = ch
        return ch

    def get(self, user_id: int) -> Challenge | None:
        return self._items.get(user_id)

    def solve(self, user_id: int, value: int) -> bool | None:
        """True: верно, False: неверно (выдана новая), None: нет капчи
        или попытки кончились (пользователь заблокирован на время)."""
        ch = self._items.get(user_id)
        if ch is None:
            return None
        if value == ch.answer:
            del self._items[user_id]
            return True
        attempts = ch.attempts + 1
        if attempts >= MAX_ATTEMPTS:
            del self._items[user_id]
            self._locked[user_id] = self._clock() + LOCK_SECONDS
            return None
        self.new(user_id, attempts)
        return False

    def _prune(self) -> None:
        now = self._clock()
        for uid, ch in list(self._items.items()):
            if now - ch.created > TTL_SECONDS:
                del self._items[uid]
