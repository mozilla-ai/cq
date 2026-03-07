.PHONY: lint format format-check test typecheck

lint:
	cd server && uv run ruff check .
	cd server && uv run ruff format --check .
	cd team-api && uv run ruff check .
	cd team-api && uv run ruff format --check .

format:
	cd server && uv run ruff format .
	cd team-api && uv run ruff format .

format-check:
	cd server && uv run ruff format --check .
	cd team-api && uv run ruff format --check .

typecheck:
	cd server && uv sync --group dev && uvx ty check craic_mcp --python .venv
	cd team-api && uv sync --group dev && uvx ty check team_api --python .venv

test:
	cd server && uv sync --group dev && uvx ty check craic_mcp --python .venv
	cd team-api && uv sync --group dev && uvx ty check team_api --python .venv
	cd server && uv run pytest
	cd team-api && uv run pytest
