"""Резервные копии базы данных.

Копия не только сохраняется на диск, но и отправляется владельцу в
Telegram. Это принципиально: копия, лежащая на том же сервере, не спасает
от потери сервера, а достать файл с телефона иначе неоткуда.
"""

from __future__ import annotations

import asyncio
import gzip
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile

from core.config import Settings
from core.logging import get_logger

log = get_logger(__name__)

#: Предел размера файла, который бот может отправить.
TELEGRAM_FILE_LIMIT = 50 * 1024 * 1024

#: Сколько ждать завершения выгрузки.
DUMP_TIMEOUT = 600


@dataclass(slots=True)
class BackupResult:
    """Чем закончилось создание копии."""

    ok: bool
    path: Path | None = None
    size: int = 0
    delivered: bool = False
    error: str = ""

    @property
    def size_mb(self) -> float:
        return self.size / 1024 / 1024


class BackupService:
    """Создаёт выгрузку базы и доставляет её владельцу."""

    def __init__(self, settings: Settings, bot: Bot, directory: Path | None = None) -> None:
        self._settings = settings
        self._bot = bot
        self._directory = directory or Path(settings.backup_dir)

    async def create(self) -> BackupResult:
        """Выгрузить базу в сжатый файл."""
        self._directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        target = self._directory / f"linkermor-{stamp}.sql.gz"
        raw = target.with_suffix("")

        if shutil.which("pg_dump") is None:
            return BackupResult(ok=False, error="pg_dump не установлен на сервере")

        command = [
            "pg_dump",
            "--host", self._settings.postgres_host,
            "--port", str(self._settings.postgres_port),
            "--username", self._settings.postgres_user,
            "--dbname", self._settings.postgres_db,
            "--no-owner",
            "--no-privileges",
            "--file", str(raw),
        ]
        environment = {"PGPASSWORD": self._settings.postgres_password.get_secret_value()}

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                env=environment,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=DUMP_TIMEOUT)
        except TimeoutError:
            return BackupResult(ok=False, error="выгрузка не уложилась в отведённое время")
        except OSError as exc:
            return BackupResult(ok=False, error=str(exc))

        if process.returncode != 0:
            detail = stderr.decode(errors="replace")[:300]
            log.error("выгрузка базы не удалась", extra={"reason": detail})
            return BackupResult(ok=False, error=detail)

        # Сжатие обязательно: текстовая выгрузка сжимается в разы, а
        # ограничение Telegram на размер файла жёсткое.
        with open(raw, "rb") as source, gzip.open(target, "wb") as archive:
            shutil.copyfileobj(source, archive)
        raw.unlink(missing_ok=True)

        size = target.stat().st_size
        log.info("копия создана", extra={"file": target.name, "size": size})
        return BackupResult(ok=True, path=target, size=size)

    async def deliver(self, result: BackupResult, owner_ids: frozenset[int]) -> BackupResult:
        """Отправить копию владельцам."""
        if not result.ok or result.path is None:
            return result

        if result.size > TELEGRAM_FILE_LIMIT:
            # Честнее сказать, что файл не влез, чем молча его не отправить.
            return BackupResult(
                ok=True,
                path=result.path,
                size=result.size,
                delivered=False,
                error=f"файл {result.size_mb:.1f} МБ больше предела Telegram",
            )

        payload = result.path.read_bytes()
        delivered = False
        for owner_id in owner_ids:
            try:
                await self._bot.send_document(
                    chat_id=owner_id,
                    document=BufferedInputFile(payload, filename=result.path.name),
                    disable_notification=True,
                )
                delivered = True
            except TelegramAPIError as exc:
                log.warning(
                    "не удалось отправить копию",
                    extra={"target_id": owner_id, "reason": str(exc)},
                )

        return BackupResult(
            ok=True, path=result.path, size=result.size, delivered=delivered
        )

    def rotate(self, keep: int) -> int:
        """Удалить старые копии, оставив последние.

        Без этого диск заполняется выгрузками, и сервер останавливается
        именно в тот момент, когда копия нужнее всего.
        """
        files = sorted(
            self._directory.glob("linkermor-*.sql.gz"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        removed = 0
        for stale in files[keep:]:
            stale.unlink(missing_ok=True)
            removed += 1
        return removed
