"""Pydantic models for cq knowledge units."""

import re
import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

from ._util import _as_list

_KU_ID_PREFIX = "ku_"
_KU_ID_PATTERN = re.compile(r"^ku_[0-9a-f]{32}$")


class Tier(StrEnum):
    """Knowledge unit storage tier."""

    LOCAL = "local"
    PRIVATE = "private"
    PUBLIC = "public"


class FlagReason(StrEnum):
    """Reason for flagging a knowledge unit."""

    STALE = "stale"
    INCORRECT = "incorrect"
    DUPLICATE = "duplicate"


class Flag(BaseModel):
    """A recorded flag against a knowledge unit."""

    reason: FlagReason
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    detail: str | None = None
    duplicate_of: str | None = None

    @model_validator(mode="after")
    def _validate_duplicate_requires_reference(self) -> "Flag":
        """Enforce that duplicate flags include a reference to the original."""
        if self.reason is FlagReason.DUPLICATE and not self.duplicate_of:
            raise ValueError("duplicate_of is required when reason is 'duplicate'")
        return self


class Insight(BaseModel):
    """Tripartite insight: summary, detail, and recommended action."""

    summary: str
    detail: str
    action: str


class Context(BaseModel):
    """Language, framework, and pattern context for a knowledge unit."""

    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    pattern: str = ""


class Evidence(BaseModel):
    """Evidence and confidence metrics for a knowledge unit."""

    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    confirmations: int = 1
    first_observed: datetime | None = None
    last_confirmed: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def _set_default_timestamps(cls, data: dict) -> dict:
        """Ensure timestamp consistency on creation."""
        if isinstance(data, dict):
            first = data.get("first_observed")
            last = data.get("last_confirmed")
            if first is None and last is None:
                now = datetime.now(UTC)
                data["first_observed"] = now
                data["last_confirmed"] = now
            elif first is None:
                data["first_observed"] = last
            elif last is None:
                data["last_confirmed"] = first
        return data


class KnowledgeUnit(BaseModel):
    """A single unit of shared agent knowledge."""

    id: str
    version: int = 1
    domains: list[str] = Field(min_length=1)
    insight: Insight
    context: Context = Field(default_factory=Context)
    evidence: Evidence = Field(default_factory=Evidence)
    tier: Tier = Tier.LOCAL
    created_by: str = ""
    superseded_by: str | None = None
    flags: list[Flag] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _validate_id_format(cls, v: str) -> str:
        """Enforce ku_ + 32 hex character ID format."""
        if not _KU_ID_PATTERN.match(v):
            raise ValueError(f"ID must match {_KU_ID_PATTERN.pattern}, got: {v!r}")
        return v

    @field_validator("superseded_by")
    @classmethod
    def _validate_superseded_by_format(cls, v: str | None) -> str | None:
        """Enforce ku_ + 32 hex character ID format for superseded_by."""
        if v is not None and not _KU_ID_PATTERN.match(v):
            raise ValueError(f"superseded_by must match {_KU_ID_PATTERN.pattern}, got: {v!r}")
        return v


def _generate_ku_id() -> str:
    """Generate a prefixed UUID for knowledge unit identification."""
    return _KU_ID_PREFIX + uuid.uuid4().hex


def create_knowledge_unit(
    *,
    domains: list[str],
    insight: Insight,
    context: Context | None = None,
    tier: Tier = Tier.LOCAL,
    created_by: str = "",
) -> KnowledgeUnit:
    """Create a new knowledge unit with an auto-generated ID."""
    domains = _as_list(domains)
    return KnowledgeUnit(
        id=_generate_ku_id(),
        domains=domains,
        insight=insight,
        context=context or Context(),
        tier=tier,
        created_by=created_by,
    )
