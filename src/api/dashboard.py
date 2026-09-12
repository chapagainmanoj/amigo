"""Authenticated canonical dashboard snapshot endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.dependencies import get_activated_user, get_store

router = APIRouter()


@router.get("/api/dashboard/snapshot")
async def get_dashboard_snapshot(
    user: Annotated[dict, Depends(get_activated_user)],
    store: Annotated[object, Depends(get_store)],
):
    return await store.get_dashboard_snapshot(user["user_id"])
