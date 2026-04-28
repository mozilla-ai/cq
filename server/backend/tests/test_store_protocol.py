"""Structural test: `SqliteStore` satisfies the async `Store` protocol.

`@runtime_checkable` protocols check attribute names only, not signatures
or sync-vs-async, so this verifies that every method name the protocol
declares exists on the concrete `SqliteStore` class.
"""

from cq_server.store import SqliteStore, Store


def test_sqlite_store_satisfies_store_protocol() -> None:
    assert issubclass(SqliteStore, Store)
