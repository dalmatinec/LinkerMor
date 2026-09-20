"""Надёжность: уведомления владельцу, проверка живости, копии базы."""

from __future__ import annotations

from pathlib import Path

import pytest
from aiogram.exceptions import TelegramForbiddenError

from cache.memory import MemoryCache
from core.backup import TELEGRAM_FILE_LIMIT, BackupResult, BackupService
from core.config import Settings
from core.health import ComponentState, HealthReport, HealthService
from sender.notifier import HOURLY_LIMIT, OwnerNotifier
from tasks.health import make_health_task
from tests.conftest import FAKE_TOKEN
from tests.fakes import FakeBot

OWNER_ID = 8243233601
OWNERS = frozenset({OWNER_ID})


@pytest.fixture
def cache() -> MemoryCache:
    return MemoryCache()


@pytest.fixture
def bot() -> FakeBot:
    return FakeBot()


@pytest.fixture
def notifier(bot, cache) -> OwnerNotifier:
    return OwnerNotifier(bot, OWNERS, cache)


# ─── Уведомления ─────────────────────────────────────────────────────────────


async def test_owner_receives_notification(bot, notifier) -> None:
    assert await notifier.notify("Что-то сломалось") is True
    assert bot.called("send_message").kwargs["chat_id"] == OWNER_ID


async def test_same_problem_is_reported_once(bot, notifier) -> None:
    """Одна ошибка в людном чате повторится тысячу раз за минуту."""
    first = await notifier.notify("Сбой", signature="db-down")
    second = await notifier.notify("Сбой", signature="db-down")

    assert first is True
    assert second is False
    assert len(bot.calls) == 1


async def test_different_problems_are_both_reported(bot, notifier) -> None:
    await notifier.notify("Сбой базы", signature="db")
    await notifier.notify("Сбой Redis", signature="redis")

    assert len(bot.calls) == 2


async def test_hourly_limit_protects_from_flood(bot, notifier) -> None:
    """Когда ломается сразу всё, поток сообщений бесполезен."""
    for index in range(HOURLY_LIMIT + 5):
        await notifier.notify("Сбой", signature=f"problem-{index}")

    assert len(bot.calls) == HOURLY_LIMIT


async def test_forced_notification_ignores_limits(bot, notifier) -> None:
    """Запуск и остановка доходят всегда."""
    for index in range(HOURLY_LIMIT + 2):
        await notifier.notify("Сбой", signature=f"p-{index}")

    assert await notifier.notify("Бот запущен", force=True) is True


async def test_notification_without_owners_is_noop(bot, cache) -> None:
    quiet = OwnerNotifier(bot, frozenset(), cache)

    assert await quiet.notify("Сбой") is False
    assert bot.calls == []


async def test_owner_who_never_wrote_to_bot_is_not_an_error(cache) -> None:
    """Пока владелец не начал диалог, Telegram отказывает — это не поломка."""
    blocked = FakeBot(error=TelegramForbiddenError(method=None, message="blocked"))
    notifier = OwnerNotifier(blocked, OWNERS, cache)

    assert await notifier.notify("Сбой") is False


async def test_error_notification_has_a_signature(bot, notifier) -> None:
    error = ValueError("сломалось")

    first = await notifier.notify_error(error, {"handler": "cmd_ban"})
    second = await notifier.notify_error(error, {"handler": "cmd_ban"})
    other = await notifier.notify_error(error, {"handler": "cmd_mute"})

    assert first is True
    assert second is False  # та же ошибка в том же месте
    assert other is True  # то же исключение, но другое место


# ─── Проверка состояния ──────────────────────────────────────────────────────


async def test_health_report_is_ok_when_everything_works(engine, bot) -> None:
    class _Redis:
        async def ping(self) -> bool:
            return True

    report = await HealthService(engine, _Redis(), bot).check()

    assert report.ok is True
    assert len(report.components) == 3


async def test_health_report_marks_broken_component(engine, bot) -> None:
    class _BrokenRedis:
        async def ping(self) -> bool:
            raise ConnectionError("нет связи")

    report = await HealthService(engine, _BrokenRedis(), bot).check()

    assert report.ok is False
    assert [c.name for c in report.failed] == ["Redis"]
    assert "нет связи" in report.describe()


class StubHealth:
    """Проверка с заранее заданным исходом."""

    def __init__(self, ok: bool) -> None:
        self.ok = ok

    async def check(self) -> HealthReport:
        return HealthReport(
            components=[ComponentState("База данных", self.ok, "" if self.ok else "упала")]
        )


async def test_health_task_reports_failure_then_recovery(bot, notifier) -> None:
    health = StubHealth(ok=True)
    task = make_health_task(health, notifier)

    await task()  # всё в порядке: владельца не беспокоим
    assert bot.calls == []

    health.ok = False
    await task()
    assert len(bot.calls) == 1

    health.ok = True
    await task()
    assert len(bot.calls) == 2
    assert "снова в порядке" in bot.calls[-1].kwargs["text"]


async def test_watchdog_is_pinged_only_while_healthy(bot, notifier, monkeypatch) -> None:
    """Молчание — и есть сигнал тревоги для внешнего сторожа."""
    pings: list[str] = []

    async def fake_ping(url: str) -> bool:
        pings.append(url)
        return True

    monkeypatch.setattr("tasks.health.ping_watchdog", fake_ping)

    health = StubHealth(ok=True)
    task = make_health_task(health, notifier, "https://example.org/ping")

    await task()
    assert pings == ["https://example.org/ping"]

    health.ok = False
    await task()
    assert len(pings) == 1  # сбой — сигнал не подаётся


# ─── Резервные копии ─────────────────────────────────────────────────────────


@pytest.fixture
def backup_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        bot_token=FAKE_TOKEN,
        owner_ids_raw=str(OWNER_ID),
        postgres_host="127.0.0.1",
        postgres_db="linkermor_test",
        postgres_user="linkermor",
        postgres_password="linkermor",
        backup_dir=str(tmp_path),
    )


async def test_backup_creates_compressed_dump(backup_settings, bot, tmp_path) -> None:
    """Проверка на настоящей базе: выгрузка действительно создаётся."""
    result = await BackupService(backup_settings, bot).create()

    assert result.ok is True, result.error
    assert result.path is not None and result.path.exists()
    assert result.path.suffix == ".gz"
    assert result.size > 0


async def test_backup_is_sent_to_owner(backup_settings, bot) -> None:
    service = BackupService(backup_settings, bot)
    created = await service.create()

    delivered = await service.deliver(created, OWNERS)

    assert delivered.delivered is True
    assert bot.called("send_document").kwargs["filename"].endswith(".sql.gz")


async def test_oversized_backup_is_reported_not_swallowed(backup_settings, bot) -> None:
    """Честнее сказать, что файл не влез, чем молча его не отправить."""
    service = BackupService(backup_settings, bot)
    huge = BackupResult(ok=True, path=Path("/tmp/x.sql.gz"), size=TELEGRAM_FILE_LIMIT + 1)

    result = await service.deliver(huge, OWNERS)

    assert result.delivered is False
    assert "больше предела" in result.error
    assert bot.calls == []


async def test_rotation_keeps_recent_copies(backup_settings, bot, tmp_path) -> None:
    """Иначе диск заполнится копиями именно тогда, когда они нужнее всего."""
    service = BackupService(backup_settings, bot)
    for index in range(5):
        (tmp_path / f"linkermor-2026010{index}-000000.sql.gz").write_bytes(b"x")

    removed = service.rotate(keep=2)

    assert removed == 3
    assert len(list(tmp_path.glob("linkermor-*.sql.gz"))) == 2
