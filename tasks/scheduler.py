"""Простой планировщик периодических задач.

Отдельной библиотеки для этого не нужно: задач немного, и все они
однотипны — выполниться, подождать, повториться. Планировщик переживает
ошибки отдельной задачи: сбой очистки не должен останавливать остальные.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from core.logging import get_logger, new_correlation_id
from core.logging import correlation_id as correlation_id_var

log = get_logger(__name__)


@dataclass(slots=True)
class PeriodicTask:
    """Задача, выполняемая с постоянным интервалом."""

    name: str
    interval: float
    callback: Callable[[], Awaitable[None]]


class Scheduler:
    """Запускает и останавливает фоновые задачи вместе с приложением."""

    def __init__(self) -> None:
        self._tasks: list[PeriodicTask] = []
        self._running: list[asyncio.Task] = []

    def add(self, name: str, interval: float, callback: Callable[[], Awaitable[None]]) -> None:
        self._tasks.append(PeriodicTask(name=name, interval=interval, callback=callback))

    def start(self) -> None:
        for task in self._tasks:
            self._running.append(asyncio.create_task(self._run(task), name=task.name))
            log.info("фоновая задача запущена", extra={"task": task.name,
                                                       "interval": task.interval})

    async def stop(self) -> None:
        for task in self._running:
            task.cancel()
        for task in self._running:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._running.clear()

    @staticmethod
    async def _run(task: PeriodicTask) -> None:
        """Выполнять задачу до отмены, переживая её ошибки."""
        while True:
            await asyncio.sleep(task.interval)
            correlation_id_var.set(new_correlation_id())
            try:
                await task.callback()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Сбой одной задачи не должен останавливать остальные.
                log.exception("фоновая задача завершилась ошибкой", extra={"task": task.name})
