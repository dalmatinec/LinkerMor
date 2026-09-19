FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# pg_dump нужен для резервных копий базы: без него копирование молча
# не работало бы именно тогда, когда на него рассчитывают.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Зависимости отдельным слоем: пересобираются только при их изменении.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Процесс не должен работать от root.
RUN mkdir -p /app/backups \
    && useradd --create-home --uid 1000 linkermor \
    && chown -R linkermor:linkermor /app
USER linkermor

CMD ["python", "main.py"]
