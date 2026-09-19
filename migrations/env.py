"""Окружение Alembic.

Подключение берётся из конфигурации приложения, а не из alembic.ini:
пароль базы не должен лежать в файле репозитория.

Модели импортируются через реестр модулей, поэтому autogenerate видит
таблицы всех подключённых модулей без ручного списка импортов.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from core.config import get_settings
from database.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Вызов ENABLED_MODULES импортирует spec каждого модуля, а те импортируют
# свои модели — так Base.metadata наполняется без ручного списка импортов.
from core.bootstrap import ENABLED_MODULES  # noqa: E402

ENABLED_MODULES()

target_metadata = Base.metadata

config.set_main_option("sqlalchemy.url", get_settings().database_url)


def _run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,  # замечать смену типа колонки
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Сгенерировать SQL без подключения к базе."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Применить миграции через асинхронное подключение."""
    engine = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
    )
    async with engine.connect() as connection:
        await connection.run_sync(_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
