"""Run the Store SPI conformance suite against every in-tree store."""

from pathlib import Path

import pytest
from conformance import StoreFactory, conformance_store_factories, run_store_conformance


@pytest.fixture(params=["sqlite", "memory"])
def store_factory(request: pytest.FixtureRequest, tmp_path: Path) -> StoreFactory:
    """Yield a fresh-store factory for each in-tree Store implementation."""
    return conformance_store_factories(tmp_path)[request.param]


def test_store_conformance(store_factory: StoreFactory) -> None:
    run_store_conformance(store_factory)
