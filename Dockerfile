ARG PYTHON_IMAGE_VERSION=3.13-alpine@sha256:9ba6d8cbebf0fb6546ae71f2a1c14f6ffd2fdab83af7fa5669734ef30ad48844
ARG NODE_IMAGE_VERSION=22-alpine@sha256:d2166de198f26e17e5a442f537754dd616ab069c47cc57b889310a717e0abbf9

FROM node:${NODE_IMAGE_VERSION} AS frontend-build

WORKDIR /frontend

COPY frontend-react/package.json frontend-react/pnpm-lock.yaml ./
RUN npm install -g pnpm && pnpm install --frozen-lockfile

COPY frontend-react/ ./
RUN pnpm build

FROM python:${PYTHON_IMAGE_VERSION} AS poetry-base

ARG POETRY_VERSION=2.1.4

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev && \
    pip install --no-cache-dir poetry==${POETRY_VERSION} && \
    apk del \
    gcc \
    musl-dev \
    libffi-dev

FROM poetry-base AS app-env

ENV POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_NO_INTERACTION=1

WORKDIR /app

COPY backend/poetry.lock backend/pyproject.toml /app/

RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev && \
    poetry install --no-interaction --no-cache --no-root --only main && \
    apk del \
    gcc \
    musl-dev \
    libffi-dev

FROM python:${PYTHON_IMAGE_VERSION} AS app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app" \
    UVICORN_HOST="0.0.0.0" \
    UVICORN_PORT="8000" \
    STATIC_PATH="/app/static"

RUN apk add --no-cache \
    docker \
    docker-cli-compose \
    p7zip \
    restic \
    curl

WORKDIR /data

COPY backend/ /app/
COPY --from=app-env /app/.venv /app/.venv
COPY --from=frontend-build /frontend/dist /app/static

RUN mkdir -p /data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/system/health || exit 1

CMD ["uvicorn", "app.main:app", "--log-level", "debug"]
