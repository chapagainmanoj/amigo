"""Fail-closed specialized Mode admission; grants are not privacy or wellbeing approval.

These defaults deliberately prevent real participant admission while evidence is missing.
Fictional candidate evaluation substitutes the entry guard in an isolated runtime, never in the
application registry. No request, profile flag, model result or operator grant changes readiness.
"""

from dataclasses import dataclass
from datetime import datetime

from src.wellbeing import ProcessingConsent, WellbeingPolicy

wellbeing_policy = WellbeingPolicy()


@dataclass
class CoachReadiness:
    enabled: bool = False
    approved_processing_notice: bool = False
    export_delete_retention_verified: bool = False

    async def complete(self):
        return all(
            value is True
            for value in (
                self.enabled,
                self.approved_processing_notice,
                self.export_delete_retention_verified,
            )
        )


coach_readiness = CoachReadiness()


async def coach_entry_guard(context):
    if not await coach_readiness.complete():
        return (
            "Coach trial admission is unavailable while privacy and delivery "
            "prerequisites await review."
        )
    consent = await context.store.get_proactive_consent(context.user["user_id"], "coaching-v1")
    if not consent or consent.get("withdrawn_at") or consent.get("policy_version") != "coaching-v1":
        return "Coach needs separate approval of its reviewed processing notice before use."
    return None


async def reflect_entry_guard(context):
    consent = None
    if wellbeing_policy.enabled and await wellbeing_policy.readiness.complete():
        stored = await context.store.get_proactive_consent(context.user["user_id"], "reflect-v1")
        if stored:
            consent = ProcessingConsent(
                participant_id=context.user["user_id"],
                policy_version=stored["policy_version"],
                acknowledged_at=datetime.fromisoformat(stored["acknowledged_at"]),
                withdrawn_at=datetime.fromisoformat(stored["withdrawn_at"])
                if stored.get("withdrawn_at")
                else None,
                country_code=stored.get("country_code"),
            )
    decision = await wellbeing_policy.check(context.user["user_id"], consent)
    return decision.reply if not decision.allowed else None
