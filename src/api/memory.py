"""Activated, owned Memory Inspector and exact-preview actions; admission defaults off."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from src.api.dependencies import get_activated_user, get_store
from src.memory_service import PAYLOAD_FIELDS, MemoryService, memory_csv, memory_now

router = APIRouter()


async def get_memory_service(request: Request, store: Annotated[object, Depends(get_store)]):
    if not hasattr(request.app.state, "memory_service"):
        request.app.state.memory_service = MemoryService(store)
    return request.app.state.memory_service


Actor = Annotated[dict, Depends(get_activated_user)]
Service = Annotated[MemoryService, Depends(get_memory_service)]
Category = Literal["preference", "routine", "constraint", "goal", "project", "context"]
ModeScope = Literal["daily", "coach", "reflect", "recommender"]


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["save", "correct", "reconfirm", "share", "forget_all"] = "save"
    memory_id: UUID | None = None
    expected_version: int | None = Field(None, ge=1)
    category: Category | None = None
    text: str | None = Field(None, min_length=1, max_length=2000)
    scopes: list[ModeScope] | None = Field(None, min_length=1, max_length=4)
    valid_until: date | None = None


class ConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=1, max_length=256)
    enable_memory: StrictBool = False
    policy_version: str | None = Field(None, max_length=100)


class PauseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    learning: StrictBool | None = None
    use: StrictBool | None = None


class ItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    memory_id: UUID
    expected_version: int = Field(ge=1)


class TransitionRequest(ItemRequest):
    action: Literal["inactive", "use_again", "complete_goal", "cancel_goal"]


@router.get("/api/memory")
async def inspect_memory(user: Actor, service: Service):
    return JSONResponse(
        await service.inspect(user["user_id"]), headers={"Cache-Control": "no-store"}
    )


@router.get("/api/memory/export")
async def export_memory(user: Actor, service: Service, format: Literal["json", "csv"] = "json"):
    records = await service.store.export_memory_data(user["user_id"])
    headers = {
        "Cache-Control": "no-store",
        "Content-Disposition": f'attachment; filename="memory-records.{format}"',
    }
    if format == "csv":
        return Response(await memory_csv(records), media_type="text/csv", headers=headers)
    return JSONResponse(records, headers=headers)


@router.post("/api/memory/preview")
async def preview_memory(body: PreviewRequest, user: Actor, service: Service):
    payload = None
    memory_id = str(body.memory_id) if body.memory_id else None
    if body.operation != "forget_all":
        if body.operation == "save":
            if body.text is None or body.category is None:
                raise HTTPException(422, "Choose a category and the exact Memory content")
            payload = dict(
                category=body.category,
                text=body.text,
                source_mode_id="daily",
                source_channel="dashboard",
                source_message_id=None,
                source_date=memory_now(service.clock).date().isoformat(),
                creation_path="dashboard_explicit",
                scopes=body.scopes or ["daily"],
                valid_until=body.valid_until.isoformat() if body.valid_until else None,
            )
        else:
            records = await service.store.export_memory_data(user["user_id"])
            current = next(
                (
                    row
                    for row in records["memories"]
                    if row["memory_id"] == memory_id and row["version"] == body.expected_version
                ),
                None,
            )
            if current is None:
                raise HTTPException(404, "Memory unavailable or changed")
            payload = {field: current.get(field) for field in PAYLOAD_FIELDS}
            for field in ("text", "category", "scopes", "valid_until"):
                if field in body.model_fields_set:
                    value = getattr(body, field)
                    payload[field] = value.isoformat() if isinstance(value, date) else value
    try:
        preview = await service.propose(
            user["user_id"],
            payload,
            operation=body.operation,
            memory_id=memory_id,
            expected_memory_version=body.expected_version,
        )
    except ValueError:
        raise HTTPException(
            409, "Memory action unavailable or changed. Refresh and review again."
        ) from None
    return JSONResponse(preview, headers={"Cache-Control": "no-store"})


@router.post("/api/memory/confirm")
async def confirm_memory(body: ConfirmationRequest, user: Actor, service: Service):
    try:
        result = await service.confirm(
            user["user_id"],
            body.token,
            enable_memory=body.enable_memory,
            policy_version=body.policy_version,
        )
    except ValueError:
        raise HTTPException(
            409, "Memory action unavailable or changed. Refresh and review again."
        ) from None
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@router.post("/api/memory/settings")
async def memory_pauses(body: PauseRequest, user: Actor, service: Service):
    try:
        result = await service.set_pauses(
            user["user_id"], body.expected_version, learning=body.learning, use=body.use
        )
    except ValueError:
        raise HTTPException(
            409, "Memory action unavailable or changed. Refresh and review again."
        ) from None
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@router.post("/api/memory/action")
async def memory_action(body: TransitionRequest, user: Actor, service: Service):
    try:
        result = await service.transition(
            user["user_id"], str(body.memory_id), body.expected_version, body.action
        )
    except ValueError:
        raise HTTPException(
            409, "Memory action unavailable or changed. Refresh and review again."
        ) from None
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@router.post("/api/memory/forget")
async def forget_memory(body: ItemRequest, user: Actor, service: Service):
    try:
        result = await service.forget(user["user_id"], str(body.memory_id), body.expected_version)
    except ValueError:
        raise HTTPException(
            409, "Memory action unavailable or changed. Refresh and review again."
        ) from None
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@router.post("/api/memory/preview/inspect")
async def inspect_memory_preview(body: ConfirmationRequest, user: Actor, service: Service):
    try:
        result = await service.review_preview(user["user_id"], body.token)
    except ValueError:
        raise HTTPException(409, "Memory preview unavailable. Review a new preview.") from None
    return JSONResponse(result, headers={"Cache-Control": "no-store"})
