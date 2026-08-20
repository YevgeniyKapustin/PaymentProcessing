FROM python:3.12.8-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=2.4.1 \
    POETRY_NO_INTERACTION=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install "poetry==${POETRY_VERSION}" \
    && python -m venv "$VIRTUAL_ENV" \
    && poetry env use "$VIRTUAL_ENV/bin/python"

WORKDIR /build

COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

COPY README.md ./
COPY src ./src
RUN poetry install --only main


FROM python:3.12.8-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app \
        --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=builder --chown=app:app /opt/venv /opt/venv
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app alembic ./alembic

USER app

EXPOSE 8000

CMD ["uvicorn", "presentation.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
