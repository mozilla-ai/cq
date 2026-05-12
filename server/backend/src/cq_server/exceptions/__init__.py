"""Exception hierarchy used by the service layer."""

from .auth import InvalidCredentialsError
from .base import ConflictError, NotFoundError, ServiceError, UnauthorizedError, ValidationError

__all__ = [
    "ConflictError",
    "InvalidCredentialsError",
    "NotFoundError",
    "ServiceError",
    "UnauthorizedError",
    "ValidationError",
]
