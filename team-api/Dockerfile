FROM python:3.12.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.22 /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen --no-install-project

COPY team_api/ team_api/
RUN uv sync --no-dev --frozen

RUN addgroup --system app && adduser --system --ingroup app app \
    && mkdir -p /data && chown app:app /data \
    && chown -R app:app /app
USER app

EXPOSE 8742

CMD ["/app/.venv/bin/craic-team-api"]
