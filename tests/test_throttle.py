"""Ограничение частоты отправки."""

from __future__ import annotations

from sender.throttle import RateLimiter

CHAT_A = -1001111111111
CHAT_B = -1002222222222


class FakeClock:
    """Часы, которыми управляет тест: ожидание не занимает реального времени."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


async def test_first_message_goes_without_delay() -> None:
    clock = FakeClock()
    limiter = RateLimiter(clock=clock.time, sleep=clock.sleep)

    assert await limiter.acquire(CHAT_A) == 0.0


async def test_second_message_to_same_chat_waits() -> None:
    """В один чат Telegram пропускает примерно одно сообщение в три секунды."""
    clock = FakeClock()
    limiter = RateLimiter(chat_interval=3.0, clock=clock.time, sleep=clock.sleep)

    await limiter.acquire(CHAT_A)
    waited = await limiter.acquire(CHAT_A)

    assert waited == 3.0


async def test_different_chats_do_not_block_each_other() -> None:
    """Лимит чата не должен тормозить рассылку по другим чатам."""
    clock = FakeClock()
    limiter = RateLimiter(chat_interval=3.0, clock=clock.time, sleep=clock.sleep)

    await limiter.acquire(CHAT_A)
    assert await limiter.acquire(CHAT_B) == 0.0


async def test_global_rate_is_respected() -> None:
    clock = FakeClock()
    limiter = RateLimiter(chat_interval=0.0, global_rate=5, clock=clock.time, sleep=clock.sleep)

    for index in range(5):
        assert await limiter.acquire(-1000 - index) == 0.0

    # Шестая отправка за ту же секунду обязана подождать.
    assert await limiter.acquire(-2000) > 0


async def test_forgetting_chat_resets_its_limit() -> None:
    """Бот покинул чат: хранить его состояние больше незачем."""
    clock = FakeClock()
    limiter = RateLimiter(chat_interval=3.0, clock=clock.time, sleep=clock.sleep)

    await limiter.acquire(CHAT_A)
    limiter.forget(CHAT_A)

    assert await limiter.acquire(CHAT_A) == 0.0
