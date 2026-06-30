FROM node:24.16.0-alpine3.23@sha256:2bdb65ed1dab192432bc31c95f94155ca5ad7fc1392fb7eb7526ab682fa5bf14 AS frontend-build

WORKDIR /frontend

COPY frontend-react/package.json frontend-react/pnpm-lock.yaml frontend-react/pnpm-workspace.yaml ./
RUN npm install -g pnpm@11.0.9 && pnpm install --frozen-lockfile

COPY frontend-react/ ./
RUN pnpm build
RUN mkdir -p \
    dist/assets/app \
    dist/assets/fonts \
    dist/assets/media \
    dist/assets/styles \
    dist/assets/vendor \
    dist/assets/workers

FROM python:3.13.13-alpine3.23@sha256:420cd0bf0f3998275875e02ecd5808168cf0843cbb4d3c536432f729247b2acc AS backend-venv

ENV UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

ARG UV_VERSION=0.11.19

RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev

RUN pip install --no-cache-dir "uv==${UV_VERSION}"

COPY backend/pyproject.toml backend/uv.lock /app/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

FROM python:3.13.13-alpine3.23@sha256:420cd0bf0f3998275875e02ecd5808168cf0843cbb4d3c536432f729247b2acc AS app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app" \
    UVICORN_HOST="0.0.0.0" \
    UVICORN_PORT="8000" \
    STATIC_PATH="/app/static" \
    FD_BINARY_PATH="/usr/local/bin/fd" \
    MCMAP_BINARY_PATH="/usr/local/bin/mcmap" \
    RESTIC_BINARY_PATH="/usr/local/bin/restic"

RUN apk add --no-cache \
    docker \
    docker-cli-compose \
    p7zip \
    bzip2 \
    curl \
    coreutils

ARG FD_VERSION=v10.4.2
ARG FD_SHA256=e3257d48e29a6be965187dbd24ce9af564e0fe67b3e73c9bdcd180f4ec11bdde
RUN curl -L "https://github.com/sharkdp/fd/releases/download/${FD_VERSION}/fd-${FD_VERSION}-x86_64-unknown-linux-musl.tar.gz" \
      -o /tmp/fd.tar.gz \
 && echo "${FD_SHA256}  /tmp/fd.tar.gz" | sha256sum -c - \
 && tar -xzf /tmp/fd.tar.gz -C /tmp \
 && install -m 0755 "/tmp/fd-${FD_VERSION}-x86_64-unknown-linux-musl/fd" /usr/local/bin/fd \
 && rm -rf /tmp/fd.tar.gz "/tmp/fd-${FD_VERSION}-x86_64-unknown-linux-musl"

ARG RESTIC_VERSION=0.18.1
ARG RESTIC_SHA256=680838f19d67151adba227e1570cdd8af12c19cf1735783ed1ba928bc41f363d
RUN curl -L "https://github.com/restic/restic/releases/download/v${RESTIC_VERSION}/restic_${RESTIC_VERSION}_linux_amd64.bz2" \
      -o /tmp/restic.bz2 \
 && echo "${RESTIC_SHA256}  /tmp/restic.bz2" | sha256sum -c - \
 && bunzip2 -c /tmp/restic.bz2 > /usr/local/bin/restic \
 && chmod +x /usr/local/bin/restic \
 && rm /tmp/restic.bz2

ARG MCMAP_VERSION=v0.8.4
ARG MCMAP_SHA256=3160526699df40a25db684ea1c8db69edb1f5a0e3fe582e6316644fc6859808e
RUN curl -L "https://github.com/xyqyear/mcmap/releases/download/${MCMAP_VERSION}/mcmap-${MCMAP_VERSION}-x86_64-unknown-linux-musl.tar.gz" \
      -o /tmp/mcmap.tar.gz \
 && echo "${MCMAP_SHA256}  /tmp/mcmap.tar.gz" | sha256sum -c - \
 && tar -xzf /tmp/mcmap.tar.gz -C /usr/local/bin --strip-components=1 \
 && chmod +x /usr/local/bin/mcmap \
 && rm /tmp/mcmap.tar.gz

WORKDIR /data

COPY --link --from=backend-venv /app/.venv /app/.venv
COPY --link backend/pyproject.toml /app/pyproject.toml
COPY --link backend/alembic.ini /app/alembic.ini
COPY --link backend/alembic /app/alembic
COPY --link backend/app /app/app
COPY --link --from=frontend-build /frontend/dist/static /app/static/static
COPY --link --from=frontend-build /frontend/dist/assets/vendor /app/static/assets/vendor
COPY --link --from=frontend-build /frontend/dist/assets/workers /app/static/assets/workers
COPY --link --from=frontend-build /frontend/dist/assets/fonts /app/static/assets/fonts
COPY --link --from=frontend-build /frontend/dist/assets/media /app/static/assets/media
COPY --link --from=frontend-build /frontend/dist/assets/styles /app/static/assets/styles
COPY --link --from=frontend-build /frontend/dist/assets/app /app/static/assets/app
COPY --link --from=frontend-build /frontend/dist/robots.txt /app/static/robots.txt
COPY --link --from=frontend-build /frontend/dist/index.html /app/static/index.html

RUN mkdir -p /data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/system/health || exit 1

CMD ["uvicorn", "app.main:app", "--forwarded-allow-ips=*", "--log-level", "debug"]
