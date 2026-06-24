"""First-party and reference Store implementations for the cq SDK."""

from .memory import InMemoryStore

__all__ = ["InMemoryStore"]

try:
    from .postgres import PostgresStore

    __all__ = [*__all__, "PostgresStore"]
except ImportError:  # psycopg not installed; PostgresStore unavailable.
    pass
