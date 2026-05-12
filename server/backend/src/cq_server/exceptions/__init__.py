"""Exception hierarchy used by the service layer."""

from .api_keys import (
    APIKeyActiveLimitReachedError,
    APIKeyInvalidError,
    APIKeyNotFoundError,
    APIKeyTTLInvalidError,
)
from .auth import InvalidCredentialsError
from .base import ConflictError, NotFoundError, ServiceError, UnauthorizedError, ValidationError
from .users import UserNotFoundError

__all__ = [
    "APIKeyActiveLimitReachedError",
    "APIKeyInvalidError",
    "APIKeyNotFoundError",
    "APIKeyTTLInvalidError",
    "ConflictError",
    "InvalidCredentialsError",
    "NotFoundError",
    "ServiceError",
    "UnauthorizedError",
    "UserNotFoundError",
    "ValidationError",
]
