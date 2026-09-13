"""Shared authenticated API dependencies."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from src.auth import get_authenticated_user_id


async def get_store(request: Request):
    """Resolve the application Store wired during app construction."""
    return request.app.state.store


async def get_bot_username(request: Request) -> str:
    """Resolve the Telegram bot this deployment actually authenticated as.

    The value is only ever what ``getMe`` returned for the configured token, so a staging
    deployment cannot name the production bot. There is deliberately no fallback handle: a
    guessed one would send participants to another environment's bot, which is exactly the
    resource separation staging has to prove.
    """
    username = getattr(request.app.state, "bot_username", None)
    if not username:
        raise HTTPException(
            status_code=503,
            detail="Telegram is not available yet. Try again shortly.",
        )
    return username


async def get_optional_bot_username(request: Request) -> str | None:
    """Resolve the deployment's bot identity without failing the whole read.

    Reading Activation state must keep working while Telegram is unreachable, so this returns
    ``None`` rather than raising. Callers omit the deep link instead of guessing a handle.
    """
    return getattr(request.app.state, "bot_username", None) or None


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
