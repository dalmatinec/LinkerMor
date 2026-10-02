import asyncio
import random
import time

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods import SendMessage

from bot import captcha
from bot.captcha import CaptchaStore
from bot.flood import FloodControl, Verdict
from bot.throttle import SlidingWindow, ThrottleMiddleware, is_sending


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


# ---- антифлуд входящих ------------------------------------------------------

def test_flood_allows_limit_then_mutes():
    clock = Clock()
    f = FloodControl(clock)
    results = [f.check(1, 3, 10, 30)[0] for _ in range(5)]
    assert results == [Verdict.OK] * 3 + [Verdict.WARN, Verdict.MUTED]
    clock.t = 31
    assert f.check(1, 3, 10, 30)[0] is Verdict.OK


def test_flood_window_slides():
    clock = Clock()
    f = FloodControl(clock)
    for _ in range(3):
        assert f.check(1, 3, 10, 30)[0] is Verdict.OK
    clock.t = 10.5
    assert f.check(1, 3, 10, 30)[0] is Verdict.OK


def test_flood_is_per_user_and_per_kind():
    f = FloodControl(Clock())
    for _ in range(3):
        f.check(1, 3, 10, 30)
    assert f.check(2, 3, 10, 30)[0] is Verdict.OK
    assert f.check(1, 3, 10, 30, kind="start")[0] is Verdict.OK


# ---- капча ------------------------------------------------------------------

def test_captcha_options_contain_answer():
    for seed in range(200):
        ch = captcha.generate(random.Random(seed))
        assert ch.answer in ch.options and len(set(ch.options)) == 4


def test_captcha_lock_after_attempts():
    clock = Clock()
    store = CaptchaStore(clock)
    store.new(1)
    assert store.solve(1, -1) is False
    assert store.solve(1, -1) is False
    assert store.solve(1, -1) is None
    assert store.locked_for(1) > 0
    clock.t = captcha.LOCK_SECONDS + 1
    assert store.locked_for(1) == 0


def test_captcha_correct():
    store = CaptchaStore()
    ch = store.new(7)
    assert store.solve(7, ch.answer) is True
    assert store.get(7) is None


# ---- антифлуд исходящих -----------------------------------------------------

def test_sliding_window():
    w = SlidingWindow(2, 10)
    w.record(0)
    w.record(1)
    assert w.delay(2) == 8
    assert w.delay(10.5) == 0


def test_only_sending_methods_throttled():
    assert is_sending("sendMessage") and is_sending("copyMessage")
    assert not is_sending("answerCallbackQuery") and not is_sending("sendChatAction")


async def test_group_limit_spaces_messages():
    mw = ThrottleMiddleware(global_rate=1000, private_burst=3, private_period=2, group_per_minute=2)
    mw.group = (2, 0.3)  # то же правило, но в масштабе теста
    stamps = []

    async def make_request(bot, method):
        stamps.append(time.monotonic())

    bot = Bot("1:A")
    for _ in range(3):
        await mw(make_request, bot, SendMessage(chat_id=-1, text="x"))
    assert stamps[2] - stamps[0] >= 0.29
    await bot.session.close()


async def test_order_kept_within_chat():
    mw = ThrottleMiddleware(global_rate=1000, private_burst=1, private_period=0.05, group_per_minute=20)
    order = []

    async def make_request(bot, method):
        order.append(method.text)

    bot = Bot("1:A")
    await asyncio.gather(*(mw(make_request, bot, SendMessage(chat_id=5, text=str(i))) for i in range(5)))
    assert order == [str(i) for i in range(5)]
    await bot.session.close()


async def test_retry_after_is_respected(monkeypatch):
    mw = ThrottleMiddleware(global_rate=1000, private_burst=5, private_period=1, group_per_minute=20)
    calls = 0
    slept = []

    async def fake_sleep(s):
        slept.append(s)

    async def make_request(bot, method):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TelegramRetryAfter(method=method, message="flood", retry_after=3)
        return "ok"

    monkeypatch.setattr("bot.throttle.asyncio.sleep", fake_sleep)
    bot = Bot("1:A")
    assert await mw(make_request, bot, SendMessage(chat_id=5, text="x")) == "ok"
    assert calls == 2 and slept and slept[-1] >= 3
    await bot.session.close()
