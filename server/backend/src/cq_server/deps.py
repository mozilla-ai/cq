"""FastAPI dependencies shared across routers."""

from fastapi import Request

from .store import TeamStore


def get_store(request: Request) -> TeamStore:
    """FastAPI dependency that returns the store from app state.

    Args:
        request: The incoming FastAPI request.

    Returns:
        The TeamStore instance attached to the application state.
    """
    return request.app.state.store
