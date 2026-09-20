"""Сопоставление сообщений с ключевыми словами."""

from __future__ import annotations

import pytest

from mod_triggers.matcher import (
    TriggerPatternError,
    TriggerRule,
    find_match,
    matches,
    normalize,
    validate_pattern,
)
from mod_triggers.models import MatchType


def rule(key: str, match_type: str = MatchType.WORD, trigger_id: int = 1) -> TriggerRule:
    return TriggerRule(id=trigger_id, key=key, match_type=match_type)


def test_normalize_collapses_spaces_and_case() -> None:
    assert normalize("  Добрый   ДЕНЬ ") == "добрый день"


# ─── Границы слова ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Привет!", True),
        ("привет всем", True),
        ("Ну привет.", True),
        ("приветствие", False),
        ("бонжур", False),
    ],
)
def test_word_match_respects_boundaries(message: str, expected: bool) -> None:
    """«привет» не должен срабатывать внутри слова «приветствие»."""
    assert matches(rule("привет"), message) is expected


def test_word_match_works_for_latin() -> None:
    assert matches(rule("hello"), "Hello there") is True
    assert matches(rule("hello"), "helloween") is False


def test_match_is_case_insensitive() -> None:
    assert matches(rule("привет"), "ПРИВЕТ") is True


# ─── Прочие режимы ───────────────────────────────────────────────────────────


def test_exact_match_requires_whole_message() -> None:
    exact = rule("правила", MatchType.EXACT)
    assert matches(exact, "правила") is True
    assert matches(exact, "  Правила  ") is True
    assert matches(exact, "где правила") is False


def test_contains_match_works_inside_words() -> None:
    assert matches(rule("прив", MatchType.CONTAINS), "приветствие") is True


def test_regex_match() -> None:
    assert matches(rule(r"куп(ить|лю)", MatchType.REGEX), "куплю аккаунт") is True
    assert matches(rule(r"куп(ить|лю)", MatchType.REGEX), "продам") is False


# ─── Разрешение конфликтов ───────────────────────────────────────────────────


def test_longer_key_wins() -> None:
    """Иначе «добрый день» перехватывался бы триггером «день»."""
    rules = [rule("день", trigger_id=1), rule("добрый день", trigger_id=2)]

    assert find_match(rules, "Добрый день, коллеги").key == "добрый день"


def test_order_of_creation_does_not_matter() -> None:
    forward = [rule("день", trigger_id=1), rule("добрый день", trigger_id=2)]
    backward = [rule("добрый день", trigger_id=2), rule("день", trigger_id=1)]

    assert find_match(forward, "добрый день") == find_match(backward, "добрый день")


def test_no_match_returns_none() -> None:
    assert find_match([rule("привет")], "совсем другое") is None


def test_empty_message_never_matches() -> None:
    assert find_match([rule("привет")], "") is None


# ─── Проверка ключа ──────────────────────────────────────────────────────────


def test_empty_key_rejected() -> None:
    with pytest.raises(TriggerPatternError):
        validate_pattern("   ", MatchType.WORD)


def test_broken_regex_rejected_at_creation() -> None:
    """Ошибку в выражении администратор увидит сразу, а не при срабатывании."""
    with pytest.raises(TriggerPatternError):
        validate_pattern("куп(ить", MatchType.REGEX)


def test_overlong_regex_rejected() -> None:
    with pytest.raises(TriggerPatternError):
        validate_pattern("a" * 500, MatchType.REGEX)


def test_long_message_is_truncated_before_scan() -> None:
    """Защита от тяжёлых выражений на огромных сообщениях."""
    from mod_triggers.matcher import MAX_SCAN_LENGTH

    message = "x" * MAX_SCAN_LENGTH + " привет"
    assert matches(rule("привет"), message) is False
