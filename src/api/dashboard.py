"""Authenticated canonical dashboard snapshot endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from src.auth import get_authenticated_user_id

router = APIRouter()


async def get_store(request: Request):
    return request.app.state.store


@router.get("/api/dashboard/snapshot")
async def get_dashboard_snapshot(
    auth_id: Annotated[str, Depends(get_authenticated_user_id)],
    store: Annotated[object, Depends(get_store)],
):
    user = await store.get_user_by_auth_id(auth_id)
    if not user:
        raise HTTPException(status_code=404, detail="User profile not paired with Telegram yet.")
    return await store.get_dashboard_snapshot(user["user_id"])
