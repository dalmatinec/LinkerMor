"""Общие фикстуры тестов."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cache.memory import MemoryCache  # noqa: E402
from core.config import Settings  # noqa: E402

#: Токен формата Telegram, не принадлежащий реальному боту.
FAKE_TOKEN = "123456789:TESTTESTTESTTESTTESTTESTTESTTESTTES"


@pytest.fixture
def settings() -> Settings:
    """Валидная конфигурация без чтения .env."""
    return Settings(
        _env_file=None,
        bot_token=FAKE_TOKEN,
        owner_ids_raw="111,222",
        postgres_password="secret",
    )


@pytest.fixture
def cache() -> MemoryCache:
    return MemoryCache()


@pytest.fixture
def project_root() -> Path:
    return PROJECT_ROOT
