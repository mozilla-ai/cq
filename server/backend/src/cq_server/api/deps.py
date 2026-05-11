"""FastAPI dependencies and the typed ``Annotated[..., Depends(...)]`` aliases routes consume.

The naming convention is ``XDep`` for every dependency type a route may
list in its parameters. Routes never call ``Depends(...)`` directly —
they import ``XDep`` and use it as the parameter type.

The factory functions are exported as well so tests can override them
through ``app.dependency_overrides``.
"""

from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import BackgroundTasks, Depends, HTTPException, Request

from ..auth import verify_token
from ..core.config import Settings
from ..core.db import Database
from ..repositories import APIKeyRepository, KnowledgeRepository, ReviewRepository, UserRepository
from ..services import APIKeyService, AuthService, KnowledgeService, ReviewService


def get_settings(request: Request) -> Settings:
    """Return the ``Settings`` instance attached at lifespan startup."""
    return request.app.state.settings


SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_database(request: Request) -> Database:
    """Return the shared ``Database`` engine wrapper."""
    return request.app.state.database


DatabaseDep = Annotated[Database, Depends(get_database)]


def get_api_key_repository(db: DatabaseDep) -> APIKeyRepository:
    """API-key repository, scoped to the per-request dependency graph."""
    return APIKeyRepository(db)


APIKeyRepositoryDep = Annotated[APIKeyRepository, Depends(get_api_key_repository)]


def get_knowledge_repository(db: DatabaseDep) -> KnowledgeRepository:
    """Knowledge-unit repository."""
    return KnowledgeRepository(db)


KnowledgeRepositoryDep = Annotated[KnowledgeRepository, Depends(get_knowledge_repository)]


def get_review_repository(db: DatabaseDep) -> ReviewRepository:
    """Review-status repository."""
    return ReviewRepository(db)


ReviewRepositoryDep = Annotated[ReviewRepository, Depends(get_review_repository)]


def get_user_repository(db: DatabaseDep) -> UserRepository:
    """User-account repository."""
    return UserRepository(db)


UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]


def get_api_key_service(
    api_keys: APIKeyRepositoryDep,
    users: UserRepositoryDep,
    settings: SettingsDep,
) -> APIKeyService:
    """Compose ``APIKeyService`` from its repositories and the API-key pepper."""
    return APIKeyService(api_keys=api_keys, users=users, pepper=settings.api_key_pepper)


APIKeyServiceDep = Annotated[APIKeyService, Depends(get_api_key_service)]


def get_auth_service(users: UserRepositoryDep, settings: SettingsDep) -> AuthService:
    """Compose ``AuthService`` from the user repository and the JWT secret."""
    return AuthService(users=users, jwt_secret=settings.jwt_secret)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def get_knowledge_service(knowledge: KnowledgeRepositoryDep) -> KnowledgeService:
    """Compose ``KnowledgeService`` from the knowledge repository."""
    return KnowledgeService(knowledge=knowledge)


KnowledgeServiceDep = Annotated[KnowledgeService, Depends(get_knowledge_service)]


def get_review_service(
    reviews: ReviewRepositoryDep,
    knowledge: KnowledgeRepositoryDep,
) -> ReviewService:
    """Compose ``ReviewService`` from the review and knowledge repositories."""
    return ReviewService(reviews=reviews, knowledge=knowledge)


ReviewServiceDep = Annotated[ReviewService, Depends(get_review_service)]


def get_current_user(request: Request, settings: SettingsDep) -> str:
    """FastAPI dependency that extracts and validates the JWT from the Authorization header.

    Verification routes through ``settings.jwt_secret`` (the same source
    ``AuthService`` signs with) so test overrides via
    ``app.dependency_overrides[get_settings]`` apply consistently to both
    sides of the JWT lifecycle.

    Args:
        request: The incoming FastAPI request.
        settings: Application settings; the JWT signing secret is read here.

    Returns:
        The username extracted from the validated token.

    Raises:
        HTTPException: With status 401 if the header is missing, malformed, or the token is invalid.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = auth_header.removeprefix("Bearer ")
    try:
        payload = verify_token(token, secret=settings.jwt_secret)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    return payload["sub"]


CurrentUserDep = Annotated[str, Depends(get_current_user)]


async def require_api_key(
    request: Request,
    background_tasks: BackgroundTasks,
    api_keys: APIKeyServiceDep,
) -> str:
    """Authenticate an API key and return the owning user's username.

    The ``Authorization: Bearer <token>`` header must carry a valid,
    unrevoked, unexpired key. ``APIKeyService.authenticate`` performs the
    HMAC-compare and schedules the ``last_used_at`` background update.

    Args:
        request: The incoming FastAPI request.
        background_tasks: FastAPI background tasks used to record usage.
        api_keys: The API-key service, supplied via dependency injection.

    Returns:
        The username of the authenticated caller.

    Raises:
        HTTPException: 401 on any authentication failure.
    """
    header = request.headers.get("Authorization")
    if not header or not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return await api_keys.authenticate(header.removeprefix("Bearer "), background_tasks)


APIKeyAuthDep = Annotated[str, Depends(require_api_key)]
