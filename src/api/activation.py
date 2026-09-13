"""Authenticated Dashboard-first Activation Journey endpoints."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.activation import (
    ACTIVATION_POLICY_VERSION,
    proposed_test_time,
    validate_preferred_name,
    validate_quiet_hours,
    validate_timezone,
)
from src.api.dependencies import get_optional_bot_username, get_store
from src.auth import AuthenticatedIdentity, get_authenticated_identity
from src.commands.activation import CreateActivationTestCommand
from src.commands.base import (
    CommandContext,
    IdempotencyConflictError,
    PairingChangedError,
)
from src.utils import default_clock

router = APIRouter()


class AcknowledgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_version: str
    beta_limits: bool
    privacy_and_retention: bool
    participant_rights: bool
    non_clinical: bool


class ProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_name: str = Field(min_length=1, max_length=80)
    timezone: str = Field(min_length=1, max_length=100)
    wake_time: str
    sleep_time: str


class TestReminderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheduled_at: datetime
    timezone: str = Field(min_length=1, max_length=100)
    exact_time_confirmed: bool
    retry: bool = False


def _require_verified(identity: AuthenticatedIdentity) -> None:
    if not identity.email_verified:
        raise HTTPException(status_code=403, detail="Verify your email before continuing setup.")


@router.get("/api/activation")
async def get_activation(
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    store: Annotated[object, Depends(get_store)],
    bot_username: Annotated[str | None, Depends(get_optional_bot_username)] = None,
):
    state = await store.get_activation_state(identity.auth_id)
    state["email_verified"] = identity.email_verified
    # The return path to Telegram has no Pairing token to carry, so it cannot reuse
    # ``bot_link`` from the Pairing endpoint. The dashboard must still never name a bot
    # itself: an environment that hardcodes one deep-links its participants into another
    # environment's bot.
    state["telegram_url"] = f"https://t.me/{bot_username}" if bot_username else None
    if not identity.email_verified:
        state["step"] = "email_verification"
        state["completed"] = False
    if (
        state.get("profile")
        and (state["step"] == "test_reminder" or state["test"].get("can_retry"))
    ):
        state["proposal"] = proposed_test_time(
            state["profile"]["timezone"], default_clock.utc_now()
        )
    return state


@router.post("/api/activation/acknowledge")
async def acknowledge_activation(
    acknowledgement: AcknowledgeRequest,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    store: Annotated[object, Depends(get_store)],
    bot_username: Annotated[str | None, Depends(get_optional_bot_username)] = None,
):
    _require_verified(identity)
    if acknowledgement.policy_version != ACTIVATION_POLICY_VERSION:
        raise HTTPException(
            status_code=409,
            detail="Review the current beta terms before continuing.",
        )
    if not all(
        (
            acknowledgement.beta_limits,
            acknowledgement.privacy_and_retention,
            acknowledgement.participant_rights,
            acknowledgement.non_clinical,
        )
    ):
        raise HTTPException(status_code=422, detail="All setup acknowledgements are required.")
    await store.acknowledge_activation_terms(identity.auth_id, ACTIVATION_POLICY_VERSION)
    return await get_activation(identity, store, bot_username)


@router.post("/api/activation/profile")
async def update_activation_profile(
    profile: ProfileRequest,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    store: Annotated[object, Depends(get_store)],
    bot_username: Annotated[str | None, Depends(get_optional_bot_username)] = None,
):
    _require_verified(identity)
    # These validators are the only normalizer in the stack, so their rejections are
    # ordinary bad input and must be 400s, not unhandled 500s.
    try:
        name = validate_preferred_name(profile.preferred_name)
        timezone = validate_timezone(profile.timezone)
        wake_time, sleep_time = validate_quiet_hours(profile.wake_time, profile.sleep_time)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None
    try:
        await store.update_activation_profile(
            identity.auth_id,
            name=name,
            timezone=timezone,
            wake_time=wake_time,
            sleep_time=sleep_time,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    return await get_activation(identity, store, bot_username)


@router.post("/api/activation/test-reminder", status_code=202)
async def create_activation_test_reminder(
    request: TestReminderRequest,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=200)
    ],
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    store: Annotated[object, Depends(get_store)],
):
    _require_verified(identity)
    if not request.exact_time_confirmed:
        raise HTTPException(status_code=422, detail="Confirm the exact test Reminder time first.")
    user = await store.get_user_by_auth_id(identity.auth_id)
    if not user:
        raise HTTPException(status_code=409, detail="Connect Telegram before creating the test.")
    try:
        result = await CreateActivationTestCommand(store).run(
            CommandContext(user["user_id"], "dashboard", idempotency_key),
            scheduled_at=request.scheduled_at,
            timezone=request.timezone,
            retry=request.retry,
        )
    except PairingChangedError as error:
        # Nothing was written, and the next attempt derives the now-correct identity, so this
        # is a retry instruction rather than a failure the participant has to resolve.
        raise HTTPException(
            status_code=409, detail=str(error), headers={"X-Retryable": "true"}
        ) from None
    except IdempotencyConflictError:
        raise HTTPException(status_code=409, detail="Idempotency key conflict.") from None
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    return result
