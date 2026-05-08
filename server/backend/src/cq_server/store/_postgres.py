"""PostgresStore: psycopg v3-backed implementation of the async Store protocol.

Phase 2 stub. Construction raises ``NotImplementedError`` pointing at the
implementation issue (#312) so that the URL → backend dispatch in
``create_store`` is wired up now and Phase 2 only needs to fill in the
class body.
"""

from __future__ import annotations


class PostgresStore:
    """psycopg v3-backed Store. Implementation lands in #312."""

    def __init__(self, database_url: str) -> None:
        raise NotImplementedError(
            "PostgresStore is not implemented yet; the psycopg v3-backed "
            "implementation lands in epic #257 (issue #312). "
            f"Got database URL: {database_url!r}"
        )
