FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    HF_HOME=/models_cache \
    SENTENCE_TRANSFORMERS_HOME=/models_cache

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
        libpq-dev \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml README.md LICENSE alembic.ini ./
COPY src/ ./src/
COPY alembic/ ./alembic/

RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

ENV PATH="/opt/venv/bin:${PATH}"

CMD ["celery", "-A", "agentstack.workers.celery_app", "worker", "--loglevel=info", "--concurrency=2"]
