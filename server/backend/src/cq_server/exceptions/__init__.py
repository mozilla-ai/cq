"""Exception hierarchy used by the service layer."""

from .api_keys import (
    APIKeyActiveLimitReachedError,
    APIKeyInvalidError,
    APIKeyNotFoundError,
    APIKeyTTLInvalidError,
)
from .auth import InvalidCredentialsError
from .base import ConflictError, NotFoundError, ServiceError, UnauthorizedError, ValidationError
from .knowledge import InvalidDomainError, KnowledgeUnitNotFoundError
from .review import KnowledgeUnitAlreadyReviewedError
from .users import UserNotFoundError

__all__ = [
    "APIKeyActiveLimitReachedError",
    "APIKeyInvalidError",
    "APIKeyNotFoundError",
    "APIKeyTTLInvalidError",
    "ConflictError",
    "InvalidCredentialsError",
    "InvalidDomainError",
    "KnowledgeUnitAlreadyReviewedError",
    "KnowledgeUnitNotFoundError",
    "NotFoundError",
    "ServiceError",
    "UnauthorizedError",
    "UserNotFoundError",
    "ValidationError",
]
