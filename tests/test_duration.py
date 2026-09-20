"""Разбор сроков наказаний."""

from __future__ import annotations

from datetime import timedelta

import pytest

from resolver.duration import DurationError, format_duration, parse_duration


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("30m", timedelta(minutes=30)),
        ("2h", timedelta(hours=2)),
        ("7d", timedelta(days=7)),
        ("1w", timedelta(weeks=1)),
        ("1d12h", timedelta(days=1, hours=12)),
        ("1h 30m", timedelta(hours=1, minutes=30)),
    ],
)
def test_english_units(text: str, expected: timedelta) -> None:
    assert parse_duration(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("30м", timedelta(minutes=30)),
        ("2ч", timedelta(hours=2)),
        ("7д", timedelta(days=7)),
        ("45сек", timedelta(seconds=45)),
    ],
)
def test_russian_units(text: str, expected: timedelta) -> None:
    """Администратор пишет по-русски чаще, чем латиницей."""
    assert parse_duration(text) == expected


def test_bare_number_means_minutes() -> None:
    assert parse_duration("45") == timedelta(minutes=45)


@pytest.mark.parametrize("text", ["навсегда", "forever", "0", "", None])
def test_permanent(text: str | None) -> None:
    assert parse_duration(text) is None


@pytest.mark.parametrize("text", ["10s", "20с"])
def test_too_short_becomes_permanent(text: str) -> None:
    """Telegram трактует ограничение короче 30 секунд как вечное.

    Если этого не учесть, администратор увидит «на 10 секунд», а человек
    останется в муте навсегда.
    """
    assert parse_duration(text) is None


def test_too_long_becomes_permanent() -> None:
    assert parse_duration("400d") is None


@pytest.mark.parametrize("text", ["завтра", "скоро", "5щ", "абв"])
def test_unparseable_rejected(text: str) -> None:
    with pytest.raises(DurationError):
        parse_duration(text)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (timedelta(days=1), "1 день"),
        (timedelta(days=2), "2 дня"),
        (timedelta(days=5), "5 дней"),
        (timedelta(days=11), "11 дней"),
        (timedelta(days=21), "21 день"),
        (timedelta(hours=1), "1 час"),
        (timedelta(hours=3), "3 часа"),
        (timedelta(minutes=1), "1 минуту"),
        (timedelta(minutes=2), "2 минуты"),
        (timedelta(minutes=5), "5 минут"),
        (None, "навсегда"),
    ],
)
def test_russian_plural_forms(value: timedelta | None, expected: str) -> None:
    """«1 день», «2 дня», «5 дней» — иначе бот выглядит неряшливо."""
    assert format_duration(value) == expected


def test_format_shows_two_largest_units() -> None:
    assert format_duration(timedelta(days=1, hours=12, minutes=30)) == "1 день 12 часов"


def test_round_trip() -> None:
    assert format_duration(parse_duration("2h30m")) == "2 часа 30 минут"
