<!-- Assembled by /setup-project from agent-pragma -->
<!-- Language: python -->
<!-- Re-run /setup-project to regenerate -->

---
paths:
  - "plugins/craic/server/**/*.py"
  - "team-api/**/*.py"
---

# Python Language Rules

## Style

- Follow PEP 8 for code style.
- Use Google-style docstrings (Args, Returns, Raises sections).
- Use modern type hints: `str | None` not `Optional[str]`.
- End single-line comments with a full stop.

## Project Structure

- Use pyproject.toml for project configuration.
- Use Astral's uv for dependency management.
- Use src layout or app layout with clear module separation.
- Organize by layer with clear separation of concerns.

### Layered Architecture

| Layer | Responsibility | May call | Must not contain |
|-------|---------------|----------|-----------------|
| **Routes/API** | Accept requests, validate input, return responses. Thin controllers only. | Services | Business logic, DB queries, model definitions |
| **Services** | Orchestrate business logic and domain rules. | Repositories, Models | DB queries (ORM or raw SQL), HTTP concerns |
| **Repositories** | Encapsulate data access (ORM queries, raw SQL, external data fetches). | Models, DB sessions/connections | Business logic, HTTP concerns |
| **Models** | Define data structures (Pydantic schemas, SQLModel/SQLAlchemy models, dataclasses). | Other models, shared utilities (leaf layer — no imports from services, repositories, or routes) | Business logic, DB queries |

A service that only wraps single CRUD queries with no additional logic is a repository — name and locate it accordingly.

## Code Quality

- Prefer composition over inheritance.
- Use Pydantic or SQLModel for data structures.
- Use context managers for resource management.
- Use mixins for shared model fields (timestamps, primary keys).

## Error Handling

- Create custom exception hierarchies inheriting from a base ServiceError.
- Map exceptions to HTTP status codes at the route layer.
- Always chain exceptions with `raise ... from e`.
- Don't use bare `except:` clauses.

## Testability

- Extract logic that depends on framework/external state into pure functions.
- When validation depends on framework state (e.g., FastAPI request objects), create a wrapper that calls a testable pure function.
- Prefer dependency injection over global state.

## Testing

- Use pytest as the test framework.
- Use descriptive test names: `test_user_creation_fails_with_duplicate_email`.
- Consider pytest-xdist for parallel execution when test runtime becomes a bottleneck.
- Ensure tests are isolated (no shared mutable state) before enabling parallel execution.
- Use fixtures with proper scope (module/function) and cleanup.
- Mirror app structure in tests directory.

## Type Checking

- Prefer Astral's ty for new projects (faster, integrated with uv/ruff ecosystem).
- Use mypy with strict mode if already configured in the project.
- Configure ruff with pyupgrade rules.

## Validation Commands

These commands are used by `/implement` and `/review` during validation. Override in `CLAUDE.local.md` if your project uses different scripts.

- **Lint:** `uv run pre-commit run --all-files`
