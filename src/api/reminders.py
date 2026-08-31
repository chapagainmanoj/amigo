"""Dashboard Reminder command adapters."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from src.api.tasks import get_store
from src.auth import get_authenticated_user_id
from src.commands.base import CommandContext, IdempotencyConflictError
from src.commands.later import ApplyLaterCommand
from src.commands.reminders import (
    CancelReminderCommand,
    ReminderScheduleInput,
    RescheduleReminderCommand,
    ScheduleReminderCommand,
)

router = APIRouter()
IdempotencyHeader = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=200),
]


class ReminderScheduleRequest(BaseModel):
    """Exact Reminder timing; actor and resource ownership are server-derived."""

    model_config = ConfigDict(extra="forbid")

    scheduled_at: datetime
    timezone: str


class ApplyLaterRequest(BaseModel):
    """Dashboard-observed Task version for an Apply Later command."""

    model_config = ConfigDict(extra="forbid")

    expected_task_version: int = Field(ge=1)


async def _resolve_actor(store, auth_id: str) -> str:
    user = await store.get_user_by_auth_id(auth_id)
    if not user:
        raise HTTPException(status_code=404, detail="User profile not paired with Telegram yet.")
    return user["user_id"]


def _accepted(result: dict) -> JSONResponse:
    return JSONResponse(status_code=202, content=result)


def _command_error(error: ValueError) -> HTTPException:
    detail = str(error)
    status_code = 404 if "not found" in detail.lower() else 422
    return HTTPException(status_code=status_code, detail=detail)


@router.post("/api/tasks/{task_id}/reminders")
async def schedule_reminder(
    task_id: str,
    reminder_request: ReminderScheduleRequest,
    idempotency_key: IdempotencyHeader,
    auth_id: Annotated[str, Depends(get_authenticated_user_id)],
    store: Annotated[object, Depends(get_store)],
):
    actor_user_id = await _resolve_actor(store, auth_id)
    try:
        result = await ScheduleReminderCommand(store).run(
            CommandContext(actor_user_id, "dashboard", idempotency_key),
            task_id=task_id,
            schedule=ReminderScheduleInput(
                reminder_request.scheduled_at,
                reminder_request.timezone,
            ),
        )
    except IdempotencyConflictError:
        raise HTTPException(status_code=409, detail="Idempotency key conflict.") from None
    except ValueError as error:
        raise _command_error(error) from None
    return _accepted(result)


@router.post("/api/reminders/{reminder_id}/reschedule")
async def reschedule_reminder(
    reminder_id: str,
    reminder_request: ReminderScheduleRequest,
    idempotency_key: IdempotencyHeader,
    auth_id: Annotated[str, Depends(get_authenticated_user_id)],
    store: Annotated[object, Depends(get_store)],
):
    actor_user_id = await _resolve_actor(store, auth_id)
    try:
        result = await RescheduleReminderCommand(store).run(
            CommandContext(actor_user_id, "dashboard", idempotency_key),
            reminder_id=reminder_id,
            schedule=ReminderScheduleInput(
                reminder_request.scheduled_at,
                reminder_request.timezone,
            ),
        )
    except IdempotencyConflictError:
        raise HTTPException(status_code=409, detail="Idempotency key conflict.") from None
    except ValueError as error:
        raise _command_error(error) from None
    return _accepted(result)


@router.delete("/api/reminders/{reminder_id}")
async def cancel_reminder(
    reminder_id: str,
    idempotency_key: IdempotencyHeader,
    auth_id: Annotated[str, Depends(get_authenticated_user_id)],
    store: Annotated[object, Depends(get_store)],
):
    actor_user_id = await _resolve_actor(store, auth_id)
    try:
        result = await CancelReminderCommand(store).run(
            CommandContext(actor_user_id, "dashboard", idempotency_key),
            reminder_id=reminder_id,
        )
    except IdempotencyConflictError:
        raise HTTPException(status_code=409, detail="Idempotency key conflict.") from None
    except ValueError as error:
        raise _command_error(error) from None
    return _accepted(result)


@router.post("/api/reminders/{reminder_id}/later")
async def apply_later(
    reminder_id: str,
    later_request: ApplyLaterRequest,
    idempotency_key: IdempotencyHeader,
    auth_id: Annotated[str, Depends(get_authenticated_user_id)],
    store: Annotated[object, Depends(get_store)],
):
    actor_user_id = await _resolve_actor(store, auth_id)
    try:
        result = await ApplyLaterCommand(store).run(
            CommandContext(actor_user_id, "dashboard", idempotency_key),
            reminder_id=reminder_id,
            expected_task_version=later_request.expected_task_version,
        )
    except IdempotencyConflictError:
        raise HTTPException(status_code=409, detail="Idempotency key conflict.") from None
    except ValueError as error:
        status_code = 409 if "stale" in str(error).lower() else 404
        raise HTTPException(status_code=status_code, detail=str(error)) from None
    return _accepted(result)
