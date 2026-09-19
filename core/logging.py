"""Структурное логирование с correlation id (ТЗ §28).

Каждый апдейт Telegram получает correlation id, который попадает во все
записи лога, сделанные при его обработке. По нему можно собрать полную
картину одного инцидента, даже когда чаты обрабатываются параллельно.

Реализовано на стандартном ``logging``: внешние зависимости ради формата
логов проект не тянет.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

#: Контекст текущего апдейта. Пустая строка вне обработки апдейта.
correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")
update_id: ContextVar[int | None] = ContextVar("update_id", default=None)
chat_id: ContextVar[int | None] = ContextVar("chat_id", default=None)
user_id: ContextVar[int | None] = ContextVar("user_id", default=None)

_CONTEXT_VARS = {
    "correlation_id": correlation_id,
    "update_id": update_id,
    "chat_id": chat_id,
    "user_id": user_id,
}

#: Поля LogRecord, которые не являются пользовательскими extra-полями.
_STANDARD_FIELDS = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


def new_correlation_id() -> str:
    """Короткий идентификатор для одного апдейта."""
    return uuid4().hex[:12]


class ContextFilter(logging.Filter):
    """Переносит значения contextvars в каждую запись лога."""

    def filter(self, record: logging.LogRecord) -> bool:
        for name, var in _CONTEXT_VARS.items():
            if not hasattr(record, name):
                setattr(record, name, var.get())
        return True


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.__dict__.items()
        if key not in _STANDARD_FIELDS and not key.startswith("_")
    }


class JsonFormatter(logging.Formatter):
    """Одна строка JSON на запись — для продакшена и сборщиков логов."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(
            {k: v for k, v in _extras(record).items() if v is not None and v != ""}
        )
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """Читаемый формат для разработки."""

    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)-7s %(name)-28s %(message)s", "%H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        context = {k: v for k, v in _extras(record).items() if v is not None and v != ""}
        cid = context.pop("correlation_id", "")

        record.message = record.getMessage()
        record.asctime = self.formatTime(record, self.datefmt)
        line = self._style._fmt % record.__dict__

        if context:
            line += " " + " ".join(f"{k}={v}" for k, v in context.items())
        if cid:
            line = f"[{cid}] {line}"
        # Traceback дописывается последним, чтобы контекст не оказался внутри него.
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def setup_logging(level: str = "info", fmt: str = "text") -> None:
    """Настроить корневой логгер. Вызывается один раз при старте."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())
    handler.addFilter(ContextFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Библиотеки шумят на INFO: оставляем только предупреждения.
    for noisy in ("aiogram.event", "aiohttp.access", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Логгер модуля. Имя принято брать как ``__name__``."""
    return logging.getLogger(name)
