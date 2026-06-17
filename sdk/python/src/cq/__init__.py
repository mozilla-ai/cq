"""cq — Python SDK for the shared agent knowledge commons."""

from . import prompts
from .client import Client, DrainResult, FallbackError, QueryResult, RemoteError
from .models import (
    Context,
    Evidence,
    Flag,
    FlagReason,
    Insight,
    KnowledgeUnit,
    Tier,
    create_knowledge_unit,
)
from .reflect import Candidate, DefaultReflector, Reflector, ReflectResult
from .scoring import apply_confirmation, apply_flag, calculate_relevance
from .store import (
    DuplicateUnitError,
    LocalStore,
    QueryParams,
    SqliteStore,
    Store,
    StoreQueryResult,
    StoreStats,
    create_store,
    rank_candidates,
)
from .stores import InMemoryStore

__all__ = [
    "Candidate",
    "Client",
    "Context",
    "DefaultReflector",
    "DrainResult",
    "DuplicateUnitError",
    "Evidence",
    "FallbackError",
    "Flag",
    "FlagReason",
    "InMemoryStore",
    "Insight",
    "KnowledgeUnit",
    "LocalStore",
    "QueryParams",
    "QueryResult",
    "ReflectResult",
    "Reflector",
    "RemoteError",
    "SqliteStore",
    "Store",
    "StoreQueryResult",
    "StoreStats",
    "Tier",
    "apply_confirmation",
    "apply_flag",
    "calculate_relevance",
    "create_knowledge_unit",
    "create_store",
    "prompts",
    "rank_candidates",
]
