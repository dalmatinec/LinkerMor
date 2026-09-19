"""Периодическая проверка состояния и сигнал внешнему сторожу."""

from __future__ import annotations

from core.health import HealthService, ping_watchdog
from core.logging import get_logger
from sender.notifier import OwnerNotifier

log = get_logger(__name__)

#: Раз в минуту: достаточно часто, чтобы заметить сбой, и достаточно
#: редко, чтобы не создавать нагрузку самой проверкой.
HEALTH_INTERVAL = 60.0


def make_health_task(
    health: HealthService,
    notifier: OwnerNotifier,
    watchdog_url: str = "",
):
    """Собрать задачу проверки состояния.

    Владелец получает сообщение при поломке и отдельное — при
    восстановлении. Молчание между ними означает, что всё в порядке.
    """
    state = {"healthy": True}

    async def run() -> None:
        report = await health.check()

        if watchdog_url and report.ok:
            # Сигнал подаётся только при исправном состоянии: сторож
            # должен поднять тревогу и при поломке, и при полном молчании.
            await ping_watchdog(watchdog_url)

        if report.ok:
            if not state["healthy"]:
                state["healthy"] = True
                await notifier.notify(
                    f"Бот снова в порядке.\n\n{report.describe()}", force=True
                )
            return

        failures = ", ".join(component.name for component in report.failed)
        log.error("проверка состояния не пройдена", extra={"failed": failures})

        was_healthy = state["healthy"]
        state["healthy"] = False
        await notifier.notify(
            f"Сбой в работе бота: {failures}\n\n{report.describe()}",
            signature=f"health:{failures}",
            force=was_healthy,
        )

    return run
