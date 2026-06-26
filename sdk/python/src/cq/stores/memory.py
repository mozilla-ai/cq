"""In-memory reference Store implementation.

A dependency-free store that keeps knowledge units in a dict, intended as
the fastest conformance fixture and as worked-example documentation for
authors of bring-your-own stores. It matches the SQLite default's
observable behavior: the same error semantics, domain-tag candidate
selection, and shared ranking. It has no full-text index, so it relies on
domain matching only; per the SPI this is a hidden implementation detail,
not an advertised capability.
"""

import threading

from ..models import KnowledgeUnit, Tier
from ..store import (
    _CONFIDENCE_BUCKETS,
    _EPOCH_UTC,
    _MAX_QUERY_DOMAINS,
    _MAX_QUERY_FRAMEWORKS,
    _MAX_QUERY_LANGUAGES,
    _MAX_QUERY_LIMIT,
    DuplicateUnitError,
    QueryParams,
    StoreQueryResult,
    StoreStats,
    _normalize_domains,
    rank_candidates,
)


class InMemoryStore:
    """Map-backed Store implementation for tests and BYO examples.

    Thread-safe: a lock serializes all access so the store can be shared
    across asyncio.to_thread() executor threads.
    """

    def __init__(self) -> None:
        """Initialize an empty store."""
        self._lock = threading.Lock()
        self._closed = False
        self._units: dict[str, KnowledgeUnit] = {}

    def _check_open(self) -> None:
        """Raise if the store has been closed."""
        if self._closed:
            raise RuntimeError("store is closed")

    def close(self) -> None:
        """Drop all in-memory state and mark the store closed."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._units = {}

    def __enter__(self) -> "InMemoryStore":
        """Enter the context manager."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Exit the context manager, closing the store."""
        self.close()

    def insert(self, unit: KnowledgeUnit) -> None:
        """Insert a knowledge unit into the store.

        Raises:
            DuplicateUnitError: If a unit with the same ID already exists.
            ValueError: If domain normalization results in no valid domains.
        """
        domains = _normalize_domains(unit.domains)
        if not domains:
            raise ValueError("At least one non-empty domain is required")
        unit = unit.model_copy(update={"domains": domains}, deep=True)
        with self._lock:
            self._check_open()
            if unit.id in self._units:
                raise DuplicateUnitError(f"Knowledge unit already exists: {unit.id}")
            self._units[unit.id] = unit

    def get(self, unit_id: str) -> KnowledgeUnit | None:
        """Retrieve a knowledge unit by ID, or None if not found."""
        with self._lock:
            self._check_open()
            unit = self._units.get(unit_id)
            return unit.model_copy(deep=True) if unit is not None else None

    def all(self) -> list[KnowledgeUnit]:
        """Return every knowledge unit in the store."""
        with self._lock:
            self._check_open()
            return [u.model_copy(deep=True) for u in self._units.values()]

    def delete(self, unit_id: str) -> None:
        """Remove a knowledge unit by ID.

        Raises:
            KeyError: If no unit with the given ID exists.
        """
        with self._lock:
            self._check_open()
            if unit_id not in self._units:
                raise KeyError(f"Knowledge unit not found: {unit_id}")
            del self._units[unit_id]

    def update(self, unit: KnowledgeUnit) -> None:
        """Replace an existing knowledge unit in the store.

        Raises:
            KeyError: If no unit with the given ID exists.
            ValueError: If domain normalization results in no valid domains.
        """
        domains = _normalize_domains(unit.domains)
        if not domains:
            raise ValueError("At least one non-empty domain is required")
        unit = unit.model_copy(update={"domains": domains}, deep=True)
        with self._lock:
            self._check_open()
            if unit.id not in self._units:
                raise KeyError(f"Knowledge unit not found: {unit.id}")
            self._units[unit.id] = unit

    def query(self, params: QueryParams) -> StoreQueryResult:
        """Search for knowledge units by domain tags with relevance ranking.

        Selects units whose domain tags overlap with the query (no
        full-text), then scores and ranks via the shared ranker.

        Raises:
            ValueError: If limit is negative, exceeds the maximum, or
                language/framework counts exceed their bounds.
        """
        if params.limit < 0:
            raise ValueError("limit must be positive")
        if params.limit > _MAX_QUERY_LIMIT:
            raise ValueError(f"limit must be at most {_MAX_QUERY_LIMIT}")

        normalized = _normalize_domains(params.domains)
        if not normalized:
            return StoreQueryResult()
        if len(normalized) > _MAX_QUERY_DOMAINS:
            normalized = normalized[:_MAX_QUERY_DOMAINS]

        languages = _normalize_domains(params.languages)
        if len(languages) > _MAX_QUERY_LANGUAGES:
            raise ValueError(f"maximum number of languages ({_MAX_QUERY_LANGUAGES}) exceeded")

        frameworks = _normalize_domains(params.frameworks)
        if len(frameworks) > _MAX_QUERY_FRAMEWORKS:
            raise ValueError(f"maximum number of frameworks ({_MAX_QUERY_FRAMEWORKS}) exceeded")

        wanted = set(normalized)
        with self._lock:
            self._check_open()
            candidates = [u.model_copy(deep=True) for u in self._units.values() if wanted & set(u.domains)]

        ranked = rank_candidates(
            candidates,
            params.model_copy(update={"domains": normalized, "languages": languages, "frameworks": frameworks}),
        )
        return StoreQueryResult(units=ranked)

    def stats(self, *, recent_limit: int = 5) -> StoreStats:
        """Return aggregated statistics for the store.

        Raises:
            ValueError: If recent_limit is negative.
        """
        if recent_limit < 0:
            raise ValueError("recent_limit must be non-negative")

        with self._lock:
            self._check_open()
            units = [u.model_copy(deep=True) for u in self._units.values()]

        domain_counts: dict[str, int] = {}
        for unit in units:
            for domain in unit.domains:
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
        # Order by count descending to match the SQLite store's output.
        domain_counts = dict(sorted(domain_counts.items(), key=lambda kv: kv[1], reverse=True))

        units.sort(
            key=lambda u: u.evidence.last_confirmed or _EPOCH_UTC,
            reverse=True,
        )
        recent = units[:recent_limit]

        buckets = {label: 0 for _, label in _CONFIDENCE_BUCKETS}
        for unit in units:
            c = unit.evidence.confidence
            label = next(lb for t, lb in _CONFIDENCE_BUCKETS if c < t)
            buckets[label] += 1

        return StoreStats(
            total_count=len(units),
            domain_counts=domain_counts,
            recent=recent,
            confidence_distribution=buckets,
            tier_counts={Tier.LOCAL: len(units)},
        )
