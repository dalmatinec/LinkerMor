"""Сопоставление сообщения с ключевыми словами триггеров (ТЗ §8).

Вынесено в отдельный модуль как чистая логика: правила приходят списком,
результат зависит только от них и от текста сообщения.

Порядок разрешения конфликтов задан явно: при нескольких совпадениях
выигрывает более длинный ключ. Так «добрый день» не перехватывается
триггером «день», заведённым раньше.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from mod_triggers.models import MatchType

#: Насколько длинный текст просматривается. Ограничение защищает от
#: намеренно тяжёлых регулярных выражений на огромных сообщениях.
MAX_SCAN_LENGTH = 2000

#: Предельная длина регулярного выражения при создании триггера.
MAX_PATTERN_LENGTH = 200


class TriggerPatternError(ValueError):
    """Ключевое слово или выражение не годится."""


@dataclass(frozen=True, slots=True)
class TriggerRule:
    """Правило срабатывания в том виде, в каком оно нужно матчеру."""

    id: int
    key: str
    match_type: str
    cooldown: int = 0


def normalize(value: str) -> str:
    """Привести ключ и текст к единому виду: нижний регистр без краёв."""
    return " ".join(value.lower().split())


@lru_cache(maxsize=512)
def _compiled(key: str, match_type: str) -> re.Pattern[str]:
    """Скомпилированное выражение для правила.

    Кеш нужен, потому что одни и те же правила проверяются на каждом
    сообщении чата, а компиляция заметно дороже самого поиска.
    """
    if match_type == MatchType.REGEX:
        return re.compile(key, re.IGNORECASE | re.MULTILINE)

    escaped = re.escape(key)
    if match_type == MatchType.WORD:
        # Границы по символам слова: работает и для кириллицы.
        return re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)
    if match_type == MatchType.EXACT:
        return re.compile(rf"^{escaped}$", re.IGNORECASE)
    return re.compile(escaped, re.IGNORECASE)


def validate_pattern(key: str, match_type: str) -> None:
    """Проверить ключ при создании триггера.

    Raises:
        TriggerPatternError: ключ пуст, слишком длинный или это
            некорректное регулярное выражение.
    """
    if not key.strip():
        raise TriggerPatternError("Ключевое слово не может быть пустым")

    if match_type == MatchType.REGEX:
        if len(key) > MAX_PATTERN_LENGTH:
            raise TriggerPatternError(
                f"Выражение длиннее {MAX_PATTERN_LENGTH} символов"
            )
        try:
            re.compile(key)
        except re.error as exc:
            raise TriggerPatternError(f"Некорректное выражение: {exc}") from exc


def matches(rule: TriggerRule, message: str) -> bool:
    """Срабатывает ли правило на этом тексте."""
    scanned = message[:MAX_SCAN_LENGTH]
    if rule.match_type == MatchType.EXACT:
        return normalize(scanned) == rule.key
    return _compiled(rule.key, rule.match_type).search(scanned) is not None


def find_match(rules: list[TriggerRule], message: str) -> TriggerRule | None:
    """Найти подходящее правило.

    При нескольких совпадениях выигрывает более длинный ключ: он точнее
    описывает намерение администратора.
    """
    if not message:
        return None

    ordered = sorted(rules, key=lambda rule: (-len(rule.key), rule.id))
    for rule in ordered:
        if matches(rule, message):
            return rule
    return None
