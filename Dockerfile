FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Зависимости отдельным слоем: пересобираются только при их изменении.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Процесс не должен работать от root.
RUN useradd --create-home --uid 1000 linkermor && chown -R linkermor:linkermor /app
USER linkermor

CMD ["python", "main.py"]
