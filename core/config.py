"""Конфигурация приложения из окружения с валидацией на старте (ТЗ §29).

Секреты берутся только из окружения или файла ``.env``, который исключён
из git. В репозитории лежит лишь ``.env.example`` с заглушками.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.constants import DEFAULT_LANGUAGE
from core.errors import ConfigError

_TOKEN_RE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{30,}$")


class Settings(BaseSettings):
    """Все параметры запуска. Невалидное значение роняет процесс на старте."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    # ─── Telegram ────────────────────────────────────────────────────────────
    bot_token: SecretStr = Field(alias="BOT_TOKEN")
    owner_ids_raw: str = Field(default="", alias="OWNER_IDS")

    # ─── PostgreSQL ──────────────────────────────────────────────────────────
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="linkermor", alias="POSTGRES_DB")
    postgres_user: str = Field(default="linkermor", alias="POSTGRES_USER")
    postgres_password: SecretStr = Field(default=SecretStr(""), alias="POSTGRES_PASSWORD")
    db_pool_size: int = Field(default=10, ge=1, le=100, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=5, ge=0, le=100, alias="DB_MAX_OVERFLOW")
    db_echo: bool = Field(default=False, alias="DB_ECHO")

    # ─── Redis ───────────────────────────────────────────────────────────────
    redis_host: str = Field(default="localhost", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_db: int = Field(default=0, ge=0, alias="REDIS_DB")
    redis_password: SecretStr = Field(default=SecretStr(""), alias="REDIS_PASSWORD")

    # ─── Приложение ──────────────────────────────────────────────────────────
    log_level: Literal["debug", "info", "warning", "error"] = Field(
        default="info", alias="LOG_LEVEL"
    )
    log_format: Literal["text", "json"] = Field(default="text", alias="LOG_FORMAT")
    default_language: str = Field(default=DEFAULT_LANGUAGE, alias="DEFAULT_LANGUAGE")

    # ─── Валидация ───────────────────────────────────────────────────────────

    @field_validator("bot_token")
    @classmethod
    def _check_token(cls, value: SecretStr) -> SecretStr:
        if not _TOKEN_RE.match(value.get_secret_value()):
            raise ValueError(
                "BOT_TOKEN не похож на токен Telegram (ожидается '<digits>:<hash>'). "
                "Получите его у @BotFather."
            )
        return value

    @field_validator("owner_ids_raw")
    @classmethod
    def _check_owners(cls, value: str) -> str:
        ids = [part.strip() for part in value.split(",") if part.strip()]
        if not ids:
            raise ValueError("OWNER_IDS пуст: некому открыть Owner Panel.")
        for item in ids:
            if not item.lstrip("-").isdigit():
                raise ValueError(f"OWNER_IDS содержит не число: {item!r}")
        return value

    # ─── Производные значения ────────────────────────────────────────────────

    @computed_field  # type: ignore[prop-decorator]
    @property
    def owner_ids(self) -> frozenset[int]:
        """Telegram user_id владельцев бота."""
        return frozenset(int(p.strip()) for p in self.owner_ids_raw.split(",") if p.strip())

    @property
    def database_url(self) -> str:
        """DSN для SQLAlchemy с асинхронным драйвером.

        Намеренно обычное свойство, а не ``computed_field``: строка содержит
        пароль и не должна попадать в ``repr`` и сериализацию конфигурации.
        """
        password = self.postgres_password.get_secret_value()
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        """DSN для Redis (FSM, счётчики, токены callback)."""
        password = self.redis_password.get_secret_value()
        auth = f":{password}@" if password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    def is_owner(self, user_id: int) -> bool:
        """Единственная глобальная проверка прав во всём проекте (ТЗ §4)."""
        return user_id in self.owner_ids


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Загрузить конфигурацию один раз за процесс."""
    try:
        return Settings()  # type: ignore[call-arg]
    except Exception as exc:  # pragma: no cover - путь только для старта
        raise ConfigError(f"Некорректная конфигурация: {exc}") from exc
