FROM node:24-alpine AS frontend-build

WORKDIR /frontend

COPY frontend-react/package.json frontend-react/pnpm-lock.yaml ./
RUN npm install -g pnpm && pnpm install --frozen-lockfile

COPY frontend-react/ ./
RUN pnpm build

FROM ghcr.io/astral-sh/uv:python3.13-alpine AS backend-venv

ENV UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev

COPY backend/pyproject.toml backend/uv.lock /app/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

FROM python:3.13-alpine AS app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app" \
    UVICORN_HOST="0.0.0.0" \
    UVICORN_PORT="8000" \
    STATIC_PATH="/app/static" \
    FD_BINARY_PATH="/usr/bin/fd"

RUN apk add --no-cache \
    docker \
    docker-cli-compose \
    p7zip \
    restic \
    curl \
    fd \
    coreutils

WORKDIR /data

COPY backend/ /app/
COPY --from=backend-venv /app/.venv /app/.venv
COPY --from=frontend-build /frontend/dist /app/static

RUN mkdir -p /data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/system/health || exit 1

CMD ["uvicorn", "app.main:app", "--forwarded-allow-ips=*", "--log-level", "debug"]
