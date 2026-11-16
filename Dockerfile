FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY pyproject.toml README.md alembic.ini ./
COPY src ./src
RUN pip install --no-deps .

RUN useradd --create-home --uid 10001 app \
    && mkdir -p /data/sessions \
    && chown -R app:app /app /data

USER app

CMD ["python", "-m", "monitor.bot"]
