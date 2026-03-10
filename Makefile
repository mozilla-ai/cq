.PHONY: lint format format-check test typecheck

lint:
	cd plugins/craic/server && uv run ruff check .
	cd plugins/craic/server && uv run ruff format --check .
	cd team-api && uv run ruff check .
	cd team-api && uv run ruff format --check .

format:
	cd plugins/craic/server && uv run ruff format .
	cd team-api && uv run ruff format .

format-check:
	cd plugins/craic/server && uv run ruff format --check .
	cd team-api && uv run ruff format --check .

typecheck:
	cd plugins/craic/server && uv sync --group dev && uvx ty check craic_mcp --python .venv
	cd team-api && uv sync --group dev && uvx ty check team_api --python .venv

test:
	cd plugins/craic/server && uv sync --group dev && uvx ty check craic_mcp --python .venv
	cd team-api && uv sync --group dev && uvx ty check team_api --python .venv
	cd plugins/craic/server && uv run pytest
	cd team-api && uv run pytest
