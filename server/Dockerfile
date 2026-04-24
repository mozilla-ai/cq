# Combined cq-server image: frontend static build served by the Python backend.
#
# Build context must be the server/ directory:
#   docker build -t cq-server server/

# --- Stage 1: build the frontend static assets. ---

FROM node:22-slim AS frontend

RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /build

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ .
RUN pnpm build

# --- Stage 2: Python backend with embedded frontend. ---

FROM python:3.12.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends sqlite3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.3 /uv /uvx /bin/

WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock ./

# Install dependencies first so this layer is cached independently of
# application code changes.
RUN uv sync --no-dev --frozen --no-install-project

COPY backend/src/ src/
RUN uv sync --no-dev --frozen

# Copy the frontend build output into the package's static directory.
COPY --from=frontend /build/dist src/cq_server/static/

RUN addgroup --system app && adduser --system --ingroup app app \
    && mkdir -p /data && chown app:app /data
USER app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    CQ_DB_PATH=/data/cq.db \
    CQ_PORT=3000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=2 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${CQ_PORT}/health')"

LABEL org.opencontainers.image.source="https://github.com/mozilla-ai/cq" \
      org.opencontainers.image.description="cq knowledge store server" \
      org.opencontainers.image.licenses="Apache-2.0"

CMD ["/app/.venv/bin/cq-server"]
