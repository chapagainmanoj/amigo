"""Fail-closed specialized Mode admission; grants are not privacy or wellbeing approval.

These defaults deliberately prevent real participant admission while evidence is missing.
Two owner-controlled settings open them: COACH_TRIAL_ENABLED attests Coach readiness, and an
allowlisted full-access chat bypasses both guards. Crisis routing runs before either guard.
Fictional candidate evaluation substitutes the entry guard in an isolated runtime, never in the
application registry. No request, profile flag, model result or operator grant changes readiness.
"""

from dataclasses import dataclass
from datetime import datetime

from src.wellbeing import ProcessingConsent, WellbeingPolicy, safety_tier

wellbeing_policy = WellbeingPolicy()


async def reflect_safety_response(mode_id: str | None, text: str) -> str | None:
    """Deterministic safety response, available even while Reflect processing is disabled."""
    if mode_id not in {"reflect", "cbt"}:
        return None
    return await wellbeing_policy.referral(await safety_tier(text))


COACH_CONSENT_VERSION = "coaching-v1"
# Owner-reviewed wording. Changing it needs the owner's approval, like the privacy notice.
COACH_PROCESSING_NOTICE = (
    "Before Coach starts: Coach is a non-clinical accountability companion, not therapy or "
    "medical advice. Your goal, plan, check-ins and replies are stored with your Amigo account "
    "and processed by Amigo's AI model provider to run Coach. Coach may send check-in messages "
    "on the days you approve. You can pause or stop Coach any time, and export or delete your "
    "data from the dashboard. Tap I agree to continue."
)
COACH_CONSENT_BUTTONS = [
    [{"text": "I agree", "callback_data": f"consent:{COACH_CONSENT_VERSION}"}]
]


@dataclass
class CoachReadiness:
    enabled: bool = False
    approved_processing_notice: bool = False
    export_delete_retention_verified: bool = False

    async def complete(self):
        from src.config import settings

        if settings.coach_trial_enabled:
            return True
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
    from src.access import is_full_access_user

    if is_full_access_user(context.user):
        return None
    if not await coach_readiness.complete():
        return (
            "Coach trial admission is unavailable while privacy and delivery "
            "prerequisites await review."
        )
    consent = await context.store.get_proactive_consent(
        context.user["user_id"], COACH_CONSENT_VERSION
    )
    if (
        not consent or consent.get("withdrawn_at")
        or consent.get("policy_version") != COACH_CONSENT_VERSION
    ):
        return COACH_PROCESSING_NOTICE
    return None


async def reflect_entry_guard(context):
    from src.access import is_full_access_user

    if is_full_access_user(context.user):
        return None
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
