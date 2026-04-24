FROM node:24-alpine AS frontend-build

WORKDIR /frontend

COPY frontend-react/package.json frontend-react/pnpm-lock.yaml frontend-react/pnpm-workspace.yaml ./
RUN npm install -g pnpm@11.0.9 && pnpm install --frozen-lockfile

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
    FD_BINARY_PATH="/usr/bin/fd" \
    MCMAP_BINARY_PATH="/usr/local/bin/mcmap"

RUN apk add --no-cache \
    docker \
    docker-cli-compose \
    p7zip \
    restic \
    curl \
    fd \
    coreutils

ARG MCMAP_VERSION=v0.2.3
RUN curl -L "https://github.com/xyqyear/mcmap/releases/download/${MCMAP_VERSION}/mcmap-${MCMAP_VERSION}-x86_64-unknown-linux-musl.tar.gz" \
      -o /tmp/mcmap.tar.gz \
 && tar -xzf /tmp/mcmap.tar.gz -C /usr/local/bin \
 && chmod +x /usr/local/bin/mcmap \
 && rm /tmp/mcmap.tar.gz

WORKDIR /data

COPY --link backend/ /app/
COPY --link --from=backend-venv /app/.venv /app/.venv
COPY --link --from=frontend-build /frontend/dist /app/static

RUN mkdir -p /data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/system/health || exit 1

CMD ["uvicorn", "app.main:app", "--forwarded-allow-ips=*", "--log-level", "debug"]
