"""Pydantic models for cq knowledge units.

Every model validates on construction (and on ``model_validate``); invalid
input raises ``pydantic.ValidationError`` — for example a free-text field over
its maximum length, an array over its item cap, or a malformed id or extension
key. Each failure in ``error.errors()`` carries the field location, a message,
and the offending input.
"""

import re
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any

from cq_schema import (
    ACTION_MAX_LENGTH,
    CREATED_BY_MAX_LENGTH,
    DETAIL_MAX_LENGTH,
    DOMAIN_MAX_LENGTH,
    DOMAINS_MAX_ITEMS,
    FLAG_DETAIL_MAX_LENGTH,
    FRAMEWORK_MAX_LENGTH,
    FRAMEWORKS_MAX_ITEMS,
    LANGUAGE_MAX_LENGTH,
    LANGUAGES_MAX_ITEMS,
    PATTERN_MAX_LENGTH,
    SUMMARY_MAX_LENGTH,
)
from pydantic import AfterValidator, BaseModel, Field, ValidationInfo, field_validator, model_validator

from ._util import _as_list

_KU_ID_PREFIX = "ku_"
_KU_ID_PATTERN = re.compile(r"^ku_[0-9a-f]{32}$")
_EXTENSION_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*:\S+$")


def _max_length(limit: int) -> AfterValidator:
    """Return a validator rejecting strings longer than limit, naming the field, limit, and actual length."""

    def _validate(value: str, info: ValidationInfo) -> str:
        if len(value) > limit:
            name = info.field_name or "value"
            raise ValueError(f"{name} must be at most {limit} characters, got {len(value)}")
        return value

    return AfterValidator(_validate)


def _bounded(limit: int) -> tuple[AfterValidator, object]:
    """Return the metadata pairing an actionable length check with a declared ``maxLength``.

    The ``AfterValidator`` enforces the ceiling with a message naming the field, limit, and length; the
    ``json_schema_extra`` records the same ceiling in the generated JSON schema without enforcing it (which
    would short-circuit the message), so the limit stays discoverable and checkable against the canonical schema.
    """
    return _max_length(limit), Field(json_schema_extra={"maxLength": limit})


_Summary = Annotated[str, *_bounded(SUMMARY_MAX_LENGTH)]
_Detail = Annotated[str, *_bounded(DETAIL_MAX_LENGTH)]
_Action = Annotated[str, *_bounded(ACTION_MAX_LENGTH)]
_Domain = Annotated[str, *_bounded(DOMAIN_MAX_LENGTH)]
_Language = Annotated[str, *_bounded(LANGUAGE_MAX_LENGTH)]
_Framework = Annotated[str, *_bounded(FRAMEWORK_MAX_LENGTH)]
_Pattern = Annotated[str, *_bounded(PATTERN_MAX_LENGTH)]
_CreatedBy = Annotated[str, *_bounded(CREATED_BY_MAX_LENGTH)]
_FlagDetail = Annotated[str, *_bounded(FLAG_DETAIL_MAX_LENGTH)]


class Tier(StrEnum):
    """Knowledge unit storage tier."""

    # Locally-stored knowledge unit.
    LOCAL = "local"
    # Shared on a remote store with restricted access.
    PRIVATE = "private"
    # Publicly shared.
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
    detail: _FlagDetail | None = None
    duplicate_of: str | None = None

    @model_validator(mode="after")
    def _validate_duplicate_requires_reference(self) -> "Flag":
        """Enforce that duplicate flags include a reference to the original."""
        if self.reason is FlagReason.DUPLICATE and not self.duplicate_of:
            raise ValueError("duplicate_of is required when reason is 'duplicate'")
        return self


class Insight(BaseModel):
    """Tripartite insight: summary, detail, and recommended action."""

    summary: _Summary
    detail: _Detail
    action: _Action


class Context(BaseModel):
    """Language, framework, and pattern context for a knowledge unit."""

    languages: list[_Language] = Field(default_factory=list, max_length=LANGUAGES_MAX_ITEMS)
    frameworks: list[_Framework] = Field(default_factory=list, max_length=FRAMEWORKS_MAX_ITEMS)
    pattern: _Pattern = ""


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
    domains: list[_Domain] = Field(min_length=1, max_length=DOMAINS_MAX_ITEMS)
    insight: Insight
    context: Context = Field(default_factory=Context)
    evidence: Evidence = Field(default_factory=Evidence)
    tier: Tier = Tier.LOCAL
    created_by: _CreatedBy = ""
    superseded_by: str | None = None
    extensions: dict[str, Any] | None = None
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

    @field_validator("extensions")
    @classmethod
    def _validate_extension_keys(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        """Enforce namespace:key format on extension keys."""
        if v is None:
            return v
        bad = [k for k in v if not _EXTENSION_KEY_PATTERN.match(k)]
        if bad:
            raise ValueError(f"extension keys must match namespace:key format, got: {bad}")
        return v


def _generate_ku_id() -> str:
    """Generate a prefixed UUID for knowledge unit identification."""
    return _KU_ID_PREFIX + uuid.uuid4().hex


def create_knowledge_unit(
    *,
    domains: list[str],
    insight: Insight,
    context: Context | None = None,
    extensions: dict[str, Any] | None = None,
    tier: Tier = Tier.LOCAL,
    created_by: str = "",
) -> KnowledgeUnit:
    """Create a new knowledge unit with an auto-generated ID.

    Args:
        domains: Domain tags for the unit; at least one is required.
        insight: The tripartite insight (summary, detail, action).
        context: Optional language, framework, and pattern context.
        extensions: Optional implementation-specific namespaced fields.
        tier: Storage tier; defaults to local.
        created_by: Identifier of the creating agent or user.

    Returns:
        The validated knowledge unit.

    Raises:
        pydantic.ValidationError: If a field violates the schema, such as a
            free-text field exceeding its maximum length, an array exceeding
            its item cap, or a malformed extension key.
    """
    domains = _as_list(domains)
    return KnowledgeUnit(
        id=_generate_ku_id(),
        domains=domains,
        insight=insight,
        context=context or Context(),
        extensions=extensions,
        tier=tier,
        created_by=created_by,
    )
