"""FastAPI dependencies shared across routers."""

from fastapi import Request

from .store import RemoteStore


def get_store(request: Request) -> RemoteStore:
    """FastAPI dependency that returns the store from app state.

    Args:
        request: The incoming FastAPI request.

    Returns:
        The RemoteStore instance attached to the application state.
    """
    return request.app.state.store
