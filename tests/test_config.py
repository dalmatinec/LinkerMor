"""Конфигурация обязана падать на старте, а не в рантайме (ТЗ §29)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.config import Settings
from tests.conftest import FAKE_TOKEN


def test_valid_settings(settings: Settings) -> None:
    assert settings.owner_ids == frozenset({111, 222})
    assert settings.is_owner(111)
    assert not settings.is_owner(999)


def test_database_url_uses_async_driver(settings: Settings) -> None:
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert "secret" in settings.database_url


def test_secrets_are_not_exposed_in_repr(settings: Settings) -> None:
    """Конфигурация попадает в логи при отладке — секреты не должны утекать."""
    assert FAKE_TOKEN not in repr(settings)
    assert "secret" not in repr(settings)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("bot_token", "не-токен"),
        ("bot_token", ""),
        ("owner_ids_raw", ""),
        ("owner_ids_raw", "111,abc"),
        ("db_pool_size", 0),
    ],
)
def test_invalid_settings_rejected(field: str, value: object) -> None:
    kwargs: dict[str, object] = {
        "bot_token": FAKE_TOKEN,
        "owner_ids_raw": "111",
        field: value,
    }
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **kwargs)  # type: ignore[arg-type]
