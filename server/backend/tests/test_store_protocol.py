"""Structural test: `RemoteStore` satisfies the async `Store` protocol.

`@runtime_checkable` protocols check attribute names only, not signatures
or sync-vs-async — so today's sync `RemoteStore` qualifies as long as
every method name the protocol declares exists on the class. Once
`SqliteStore` (issue #308) replaces `RemoteStore` with an actually-async
implementation, this same test stays valid.
"""

from cq_server.store import RemoteStore, Store


def test_remote_store_satisfies_store_protocol() -> None:
    assert issubclass(RemoteStore, Store)
