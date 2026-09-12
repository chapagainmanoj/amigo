"""Shared authenticated API dependencies."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from src.auth import get_authenticated_user_id


async def get_store(request: Request):
    """Resolve the application Store wired during app construction."""
    return request.app.state.store


async def get_activated_user(
    auth_id: Annotated[str, Depends(get_authenticated_user_id)],
    store: Annotated[object, Depends(get_store)],
) -> dict:
    """Require canonical Activation completion before normal product access."""
    user = await store.get_user_by_auth_id(auth_id)
    if not user:
        raise HTTPException(status_code=404, detail="User profile not paired with Telegram yet.")
    state = await store.get_activation_state(auth_id)
    if not state.get("completed"):
        raise HTTPException(status_code=409, detail="Complete setup before using the dashboard.")
    return user
