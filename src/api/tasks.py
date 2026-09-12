"""Dashboard Task command adapter."""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from src.api.dependencies import get_activated_user, get_store
from src.commands.base import (
    CommandContext,
    IdempotencyConflictError,
    InvalidTransitionError,
    StaleVersionError,
)
from src.commands.tasks import CreateTaskCommand, CreateTaskInput, ResolveTaskCommand

router = APIRouter()


class CreateTaskRequest(BaseModel):
    """Dashboard-supplied Task fields; actor identity is resolved from authentication."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    category: Literal["health", "work", "personal", "social", "other"] = "other"
    planning_day: date | None = None


class ResolveTaskRequest(BaseModel):
    """Dashboard terminal intent; identity and current Task are server-verified."""

    model_config = ConfigDict(extra="forbid")

    outcome: Literal["completed", "skipped", "cancelled"]
    expected_version: int = Field(ge=1)


@router.post("/api/tasks")
async def create_task(
    task_request: CreateTaskRequest,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=200),
    ],
    user: Annotated[dict, Depends(get_activated_user)],
    store: Annotated[object, Depends(get_store)],
):
    """Create one Task through the canonical authenticated application command."""
    command = CreateTaskCommand(store)
    try:
        return await command.run(
            CommandContext(
                actor_user_id=user["user_id"],
                surface="dashboard",
                idempotency_key=idempotency_key,
            ),
            CreateTaskInput(
                title=task_request.title,
                category=task_request.category,
                planning_day=task_request.planning_day,
            ),
        )
    except IdempotencyConflictError:
        raise HTTPException(
            status_code=409,
            detail="Idempotency key was already used for different input.",
        ) from None


@router.post("/api/tasks/{task_id}/resolve")
async def resolve_task(
    task_id: str,
    task_request: ResolveTaskRequest,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=200),
    ],
    user: Annotated[dict, Depends(get_activated_user)],
    store: Annotated[object, Depends(get_store)],
):
    """Apply one tenant-owned terminal Task/Reminder transition."""
    try:
        result = await ResolveTaskCommand(store).run(
            CommandContext(
                actor_user_id=user["user_id"],
                surface="dashboard",
                idempotency_key=idempotency_key,
            ),
            task_id=task_id,
            outcome=task_request.outcome,
            expected_version=task_request.expected_version,
        )
    except (IdempotencyConflictError, StaleVersionError, InvalidTransitionError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    except ValueError as error:
        status_code = 404 if "not found" in str(error).lower() else 422
        raise HTTPException(status_code=status_code, detail=str(error)) from None

    status_code = 202 if result["effect_state"] == "queued" else 200
    return JSONResponse(status_code=status_code, content=result)
