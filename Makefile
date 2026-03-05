.PHONY: lint format format-check test

lint:
	cd server && uv run ruff check .
	cd team-api && uv run ruff check .

format:
	cd server && uv run ruff format .
	cd team-api && uv run ruff format .

format-check:
	cd server && uv run ruff format --check .
	cd team-api && uv run ruff format --check .

test:
	cd server && uv run pytest
	cd team-api && uv run pytest
