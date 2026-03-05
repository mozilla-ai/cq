# Pydantic model for CRAIC knowledge units.

from datetime import datetime, timezone
from enum import Enum

from nanoid import generate
from pydantic import BaseModel, Field


KU_ID_PREFIX = "ku_"
KU_ID_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
KU_ID_LENGTH = 21


class Tier(str, Enum):
    LOCAL = "local"
    TEAM = "team"
    GLOBAL = "global"


class FlagReason(str, Enum):
    STALE = "stale"
    INCORRECT = "incorrect"
    DUPLICATE = "duplicate"


class Insight(BaseModel):
    summary: str
    detail: str
    action: str


class Context(BaseModel):
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    pattern: str = ""


class Evidence(BaseModel):
    confidence: float = 0.5
    confirmations: int = 1
    first_observed: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    last_confirmed: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class KnowledgeUnit(BaseModel):
    id: str
    version: int = 1
    domain: list[str]
    insight: Insight
    context: Context = Field(default_factory=Context)
    evidence: Evidence = Field(default_factory=Evidence)
    tier: Tier = Tier.LOCAL
    created_by: str = ""
    superseded_by: str | None = None


def _generate_ku_id() -> str:
    """Generate a prefixed nanoid for knowledge unit identification."""
    return KU_ID_PREFIX + generate(KU_ID_ALPHABET, KU_ID_LENGTH)


def create_knowledge_unit(
    *,
    domain: list[str],
    insight: Insight,
    context: Context | None = None,
    tier: Tier = Tier.LOCAL,
    created_by: str = "",
) -> KnowledgeUnit:
    """Create a new knowledge unit with an auto-generated ID."""
    return KnowledgeUnit(
        id=_generate_ku_id(),
        domain=domain,
        insight=insight,
        context=context or Context(),
        tier=tier,
        created_by=created_by,
    )
