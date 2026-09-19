"""Расписание резервного копирования."""

from __future__ import annotations

from core.backup import BackupService
from core.config import Settings
from core.logging import get_logger
from sender.notifier import OwnerNotifier

log = get_logger(__name__)


def make_backup_task(
    service: BackupService, settings: Settings, notifier: OwnerNotifier
):
    """Собрать задачу создания копии.

    Об успешной копии владельцу приходит сам файл, поэтому отдельного
    сообщения не нужно. О неудаче сообщается обязательно: молчаливо
    сломавшееся резервное копирование хуже его отсутствия — на него
    рассчитывают.
    """

    async def run() -> None:
        result = await service.create()
        if not result.ok:
            await notifier.notify(
                f"Не удалось создать резервную копию базы.\n\n{result.error}",
                signature="backup-failed",
            )
            return

        delivered = await service.deliver(result, settings.owner_ids)
        removed = service.rotate(settings.backup_keep)

        if not delivered.delivered:
            await notifier.notify(
                "Копия создана, но не отправлена в Telegram.\n\n"
                f"{delivered.error or 'владелец не начал диалог с ботом'}\n"
                f"Файл на сервере: {result.path}",
                signature="backup-undelivered",
            )

        log.info(
            "резервное копирование выполнено",
            extra={"size": result.size, "delivered": delivered.delivered,
                   "rotated": removed},
        )

    return run
