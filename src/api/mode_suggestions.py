"""Owned, explicit participant opt-in; preference never bypasses release readiness."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StrictBool

from src.api.dependencies import get_activated_user, get_store

router = APIRouter()
Actor = Annotated[dict, Depends(get_activated_user)]
Store = Annotated[object, Depends(get_store)]


class PreferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool


@router.get("/api/mode-suggestions/preference")
async def suggestion_preference(user: Actor, store: Store):
    return JSONResponse(
        {"enabled": await store.get_mode_suggestion_preference(user["user_id"])},
        headers={"Cache-Control": "no-store"},
    )


@router.post("/api/mode-suggestions/preference")
async def set_suggestion_preference(body: PreferenceRequest, user: Actor, store: Store):
    try:
        enabled = await store.set_mode_suggestion_preference(user["user_id"], body.enabled)
    except ValueError:
        raise HTTPException(
            409, "Preference could not be confirmed. Refresh and try again."
        ) from None
    return JSONResponse({"enabled": enabled}, headers={"Cache-Control": "no-store"})
