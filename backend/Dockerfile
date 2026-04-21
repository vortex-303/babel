# babel backend — runs FastAPI on Fly.io. Talks to Supabase Postgres +
# Supabase Storage via env. No llama-server locally; translation happens
# on the worker (Phase C), so this image is intentionally small.
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_LINK_MODE=copy

# Build deps for psycopg (libpq) + pymupdf wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
# Editable install needs app/ present. Dep cache is still reused when
# only app/*.py changes because the layer cache keys on pyproject.toml
# (moved above) + the content of app/ via BuildKit content hashing.
RUN uv pip install --system -e .

EXPOSE 8765

# Single-process uvicorn — enough for beta traffic, no worker loop needed
# once the translate orchestrator moves to the pull-worker in Phase C.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765"]
