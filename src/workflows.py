"""Declared Coach workflow and an owned projection over its existing durable records.

This module performs no transitions. Program Commands and the delivery outbox remain the only
executors. The declaration describes current v1 semantics; it is not a persisted version binding.
"""

from dataclasses import asdict, dataclass

from src.utils import instant


@dataclass(frozen=True)
class WorkflowStep:
    id: str
    waits_for: str
    confirmation: str
    durable_owner: str


@dataclass(frozen=True)
class WorkflowDefinition:
    id: str
    mode_id: str
    version: int
    steps: tuple[WorkflowStep, ...]


COACH_WORKFLOW_V1 = WorkflowDefinition(
    id="coaching_program",
    mode_id="coach",
    version=1,
    steps=(
        WorkflowStep(
            "approval", "participant_approval", "exact_current_draft", "coaching_approvals"
        ),
        WorkflowStep("cadence", "selected_slot", "approved_program_cadence", "coaching_programs"),
        WorkflowStep(
            "delivery", "delivery_outcome", "approved_program_cadence", "coaching_delivery_outbox"
        ),
        WorkflowStep(
            "reply", "participant_reply_or_bounded_follow_up", "none", "coaching_delivery_replies"
        ),
        WorkflowStep(
            "review", "explicit_participant_choice", "current_program_change", "coaching_entries"
        ),
    ),
)


async def coaching_workflow_status(
    store, user_id: str, program_id: str | None = None
) -> dict | None:
    """Return owned content-free workflow state without claiming, waking or approving anything.

    Omit program_id to inspect the current nonterminal Program. Explicit IDs allow terminal
    inspection, subject to the same Store ownership filter. Approval tokens, goals, progress,
    provider responses and command payloads are deliberately absent.
    """
    program = await store.get_coaching_program(user_id, program_id)
    if program is None or program["user_id"] != user_id:
        return None
    history = await store.get_coaching_delivery_history(user_id, program["program_id"])
    deliveries = sorted(history.get("deliveries", []), key=lambda row: instant(row["scheduled_at"]))
    reply = instant(history["last_reply_at"]) if history.get("last_reply_at") else None
    unanswered = sum(
        row["state"] in {"accepted", "uncertain", "dispatched"}
        and (reply is None or instant(row.get("dispatched_at") or row["scheduled_at"]) > reply)
        for row in deliveries
    )
    state = program["state"]
    if state == "draft":
        waiting_for = "participant_approval"
    elif state == "paused":
        waiting_for = "explicit_resume"
    elif state != "active":
        waiting_for = "none"
    elif any(row["state"] in {"pending", "claimed", "dispatched"} for row in deliveries):
        waiting_for = "delivery_outcome"
    elif unanswered >= 2:
        waiting_for = "participant_reply"
    else:
        waiting_for = "selected_slot_or_participant_reply"
    return {
        "definition": asdict(COACH_WORKFLOW_V1),
        "version_binding": "current_code_only",
        "program_id": program["program_id"],
        "program_version": program["version"],
        "state": state,
        "waiting_for": waiting_for,
        "unanswered_deliveries": unanswered,
        "last_reply_at": history.get("last_reply_at"),
        "deliveries": [
            {
                name: row.get(name)
                for name in ("delivery_key", "local_day", "kind", "scheduled_at", "state")
            }
            for row in deliveries[-20:]
        ],
        "delivery_guarantee": "uncertain_provider_acceptance_is_not_retried",
    }
