# LinkerMor

Мультичатовый Telegram-бот для модерации: **один процесс обслуживает десятки чатов**,
и настройки каждого чата изолированы от остальных.

## Возможности

Модерация (`/ban`, `/unban`, `/mute`, `/unmute`, `/warn`, `/unwarn`, `/warns`),
триггеры, welcome с капчей,
репутация и ранги, антиспам-фильтры с белым списком пересылок, игры,
панель владельца и динамическая админ-панель для каждого чата.

Все тексты и кнопки настраиваются для каждого чата отдельно, поддерживают
премиум-эмодзи и форматирование Telegram.

## Требования

- Python 3.11+
- PostgreSQL 17
- Redis 7
- Telegram Bot API 10.3 (aiogram 3.31)

## Быстрый старт

```bash
cp .env.example .env      # заполнить BOT_TOKEN и OWNER_IDS
docker compose up -d      # postgres + redis + бот, миграции применятся сами
```

Без Docker:

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env      # заполнить
.venv/bin/alembic upgrade head
.venv/bin/python main.py
```

## Разработка

Тесты работают на настоящем PostgreSQL: проект опирается на JSONB, частичные
индексы и `ON CONFLICT`, которых нет в SQLite.

```bash
service postgresql start                      # если база ещё не запущена
createdb linkermor_test                       # один раз
.venv/bin/python -m pytest                    # тесты
.venv/bin/alembic revision --autogenerate -m "описание"
.venv/bin/alembic upgrade head
```

Адрес тестовой базы переопределяется переменной `TEST_DATABASE_URL`.

## Безопасность

`BOT_TOKEN`, пароли базы и Redis хранятся только в `.env`, который исключён из git.
В репозитории лежит `.env.example` с заглушками.

## Документация

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — устройство проекта
- [docs/DECISIONS.md](docs/DECISIONS.md) — принятые технические решения
