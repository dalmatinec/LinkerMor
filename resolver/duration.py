"""Разбор и вывод сроков наказаний.

Администратор пишет срок как придётся: ``30m``, ``2ч``, ``1d12h``, ``навсегда``.
Разбор собран в одном месте, чтобы все команды понимали одинаковый формат.

Учитывается ограничение Telegram: ограничение короче 30 секунд или длиннее
366 дней трактуется как бессрочное. Поэтому такие значения сразу приводятся
к «навсегда» — иначе администратор увидел бы в ответе «на 10 секунд», а на
деле выдал бы вечный мут.
"""

from __future__ import annotations

import re
from datetime import timedelta

from core.constants import MAX_RESTRICT_SECONDS, MIN_RESTRICT_SECONDS

#: Единицы времени в русской и английской записи.
UNITS: dict[str, int] = {
    "s": 1, "с": 1, "sec": 1, "сек": 1,
    "m": 60, "м": 60, "min": 60, "мин": 60,
    "h": 3600, "ч": 3600, "hour": 3600, "час": 3600,
    "d": 86400, "д": 86400, "day": 86400, "дн": 86400,
    "w": 604800, "н": 604800, "week": 604800, "нед": 604800,
}

#: Слова, означающие бессрочное наказание.
FOREVER_WORDS = frozenset({"0", "forever", "навсегда", "永", "permanent", "перманент", "всегда"})

_PART_RE = re.compile(r"(\d+)\s*([a-zA-Zа-яА-Я]*)")

#: Формы множественного числа для вывода срока по-русски.
_PLURALS: dict[str, tuple[str, str, str]] = {
    "day": ("день", "дня", "дней"),
    "hour": ("час", "часа", "часов"),
    "minute": ("минуту", "минуты", "минут"),
    "second": ("секунду", "секунды", "секунд"),
}


class DurationError(ValueError):
    """Срок записан в непонятном виде."""


def parse_duration(value: str | None) -> timedelta | None:
    """Разобрать срок наказания.

    Args:
        value: Строка вида ``30m``, ``2ч``, ``1d12h`` или слово «навсегда».
            Число без единицы измерения считается минутами.

    Returns:
        Длительность либо ``None`` для бессрочного наказания.

    Raises:
        DurationError: строку не удалось разобрать.
    """
    if value is None:
        return None

    text = value.strip().lower()
    if not text or text in FOREVER_WORDS:
        return None

    total = 0
    matched_length = 0
    for match in _PART_RE.finditer(text):
        amount, unit = match.group(1), match.group(2)
        matched_length += len(match.group(0))
        if not unit:
            total += int(amount) * 60  # число без единицы — минуты
            continue
        if unit not in UNITS:
            raise DurationError(f"Неизвестная единица времени: {unit}")
        total += int(amount) * UNITS[unit]

    # Строка вроде «завтра» не содержит чисел и разобрана не была.
    if total == 0 or matched_length != len(text.replace(" ", "")):
        raise DurationError(f"Не удалось разобрать срок: {value}")

    # Telegram трактует такие значения как бессрочные — не вводим в заблуждение.
    if total < MIN_RESTRICT_SECONDS or total > MAX_RESTRICT_SECONDS:
        return None

    return timedelta(seconds=total)


def _plural(number: int, forms: tuple[str, str, str]) -> str:
    """Выбрать форму слова: 1 день, 2 дня, 5 дней."""
    if 11 <= number % 100 <= 14:
        return forms[2]
    last = number % 10
    if last == 1:
        return forms[0]
    if 2 <= last <= 4:
        return forms[1]
    return forms[2]


def format_duration(value: timedelta | None, forever: str = "навсегда") -> str:
    """Показать срок человеку: ``2 часа 30 минут``."""
    if value is None:
        return forever

    seconds = int(value.total_seconds())
    parts: list[str] = []
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60), ("second", 1)):
        amount, seconds = divmod(seconds, size)
        if amount:
            parts.append(f"{amount} {_plural(amount, _PLURALS[unit])}")

    return " ".join(parts[:2]) if parts else forever
