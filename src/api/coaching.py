"""Owned Coaching Program inspection/export/deletion; no account-wide privacy claims."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from src.api.dependencies import get_activated_user, get_store
from src.workflows import coaching_workflow_status

router = APIRouter()


class DeleteCoachingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: Literal["delete my coaching records"]


@router.get("/api/coaching")
async def inspect_coaching(
    user: Annotated[dict, Depends(get_activated_user)],
    store: Annotated[object, Depends(get_store)],
):
    return await store.export_coaching_data(user["user_id"])


@router.get("/api/coaching/export")
async def export_coaching(
    user: Annotated[dict, Depends(get_activated_user)],
    store: Annotated[object, Depends(get_store)],
):
    return JSONResponse(
        await store.export_coaching_data(user["user_id"]),
        headers={
            "Content-Disposition": 'attachment; filename="coaching-records.json"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/api/coaching/delete")
async def delete_coaching(
    body: DeleteCoachingRequest,
    user: Annotated[dict, Depends(get_activated_user)],
    store: Annotated[object, Depends(get_store)],
):
    request_id = str(uuid.uuid4())
    await store.delete_coaching_data(user["user_id"], request_id)
    return {
        "status": "coaching_records_deleted",
        "request_id": request_id,
        "scope": (
            "Program records and entries only. Conversation Messages and provider copies remain."
        ),
    }


@router.get("/api/coaching/workflow")
async def inspect_coaching_workflow(
    user: Annotated[dict, Depends(get_activated_user)],
    store: Annotated[object, Depends(get_store)],
    program_id: uuid.UUID | None = None,
):
    return JSONResponse(
        await coaching_workflow_status(
            store, user["user_id"], str(program_id) if program_id is not None else None
        ),
        headers={"Cache-Control": "no-store"},
    )
