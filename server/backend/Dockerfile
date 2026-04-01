FROM python:3.12.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.22 /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
# Install dependencies first (without the project) so this layer is cached
# independently of application code changes.
RUN uv sync --no-dev --frozen --no-install-project

COPY team_api/ team_api/
RUN uv sync --no-dev --frozen

RUN addgroup --system app && adduser --system --ingroup app app \
    && mkdir -p /data && chown app:app /data
USER app

# Prevent Python from writing .pyc files (avoids permission errors writing
# into the root-owned venv at runtime) and ensure logs are not buffered.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8742

CMD ["/app/.venv/bin/cq-team-api"]
