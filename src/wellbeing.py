"""Fail-closed wellbeing entry and model-independent referral primitives.

No consent persistence, operational privacy workflows, verified resources or clinical approval
are supplied by this module. The default policy denies processing. Only trusted application
code may supply consent/readiness evidence; participant text and model output cannot authorize it.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlsplit

from src.utils import Clock, default_clock

REFLECT_CONSENT_VERSION = "reflect-sensitive-processing-v1"
STATIC_EMERGENCY_REFERRAL = (
    "Amigo cannot provide emergency help or monitor your safety. If you are in immediate danger, "
    "contact local emergency services or go to the nearest emergency department now. "
    "If possible, contact a trusted person nearby."
)
REFLECT_UNAVAILABLE = "Reflect is unavailable. Use /daily to return to Daily."
REFLECT_CONSENT_NOTICE = (
    "Reflect is a non-clinical reflection feature, not therapy or monitored support. "
    "What you share is sensitive, processed by AI and retained as Messages under the disclosed "
    "privacy policy; it is not automatically Memory, a Mood Entry or a Task. "
    "Separate processing consent is required before sharing reflection content. "
    "Declining leaves Daily available; /daily exits at any time."
)
SafetyTier = Literal["ordinary", "ambiguous", "explicit", "immediate"]


async def safety_tier(text: str) -> SafetyTier:
    """Conservative English routing rules, never a diagnosis or a clinical risk assessment.

    Known urgent statements bypass generation. These rules cannot recognize every expression
    of danger; qualified review and the remaining Reflect admission gates are still mandatory.
    """
    value = text.casefold().replace("’", "'")
    if re.search(
        r"\b(attempt (?:is )?in progress|immediate danger|"
        r"(?:i(?:'m| am) )?(?:about to kill myself|have taken an overdose)|"
        r"i(?:'m| am) going to (?:kill|hurt) myself (?:right )?now|"
        r"i (?:just )?(?:took an overdose|swallowed (?:all |a bottle of )?(?:my )?pills))\b",
        value,
    ):
        return "immediate"
    # Only negate the matched disclosure, not other thoughts in the same sentence.
    for disclosure in re.finditer(
            r"\b(?:(?:thinking|thoughts) (?:about|of) (?:suicide|killing myself|"
            r"hurting myself|self[- ]harm)|(?:i (?:want|plan|intend) to|"
            r"i(?:'m| am) going to) (?:kill|hurt) myself|i(?:'m| am) suicidal|"
            r"i (?:don't|do not) want to live)\b",
            value,
    ):
        prefix = value[max(0, disclosure.start() - 60):disclosure.start()]
        if not re.search(r"\b(?:not|never|no|no longer) (?:currently )?$", prefix):
            return "explicit"
    if re.search(r"\b(?:i (?:can't|cannot) go on|no point (?:in living|anymore))\b", value):
        return "ambiguous"
    return "ordinary"


async def reflect_safety_response(mode_id: str | None, text: str) -> str | None:
    """Deterministic safety response, available even while Reflect processing is disabled."""
    if mode_id != "reflect":
        return None
    from src.mode_readiness import wellbeing_policy

    return await wellbeing_policy.referral(await safety_tier(text))


def _utc(instant: datetime) -> datetime:
    return instant.replace(tzinfo=UTC) if instant.tzinfo is None else instant.astimezone(UTC)


@dataclass(frozen=True)
class ProcessingConsent:
    participant_id: str
    policy_version: str
    acknowledged_at: datetime
    withdrawn_at: datetime | None = None
    country_code: str | None = None  # Explicit participant selection, never inferred.


@dataclass(frozen=True)
class WellbeingReadiness:
    """Operational prerequisites; false until actual owner-reviewed evidence exists."""

    approved_notice: bool = False
    separate_consent_storage: bool = False
    history_and_summary_isolation: bool = False
    retention_enforcement: bool = False
    ownership_export_and_deletion: bool = False
    handoff_and_cache_cleanup: bool = False
    qualified_wellbeing_review: bool = False

    async def complete(self) -> bool:
        return all(
            value is True
            for value in (
                self.approved_notice,
                self.separate_consent_storage,
                self.history_and_summary_isolation,
                self.retention_enforcement,
                self.ownership_export_and_deletion,
                self.handoff_and_cache_cleanup,
                self.qualified_wellbeing_review,
            )
        )


@dataclass(frozen=True)
class WellbeingDecision:
    allowed: bool
    reason: Literal["disabled", "prerequisites_missing", "consent_required", "allowed"]
    reply: str | None


@dataclass(frozen=True)
class CrisisResource:
    """Trusted operator-maintained resource metadata; never populated by a model."""

    country_code: Literal["US", "CA"]
    service_name: str
    purpose: str
    contact_methods: tuple[str, ...]
    hours: str
    languages: tuple[str, ...]
    official_source: str
    manually_verified_at: datetime
    next_review_at: datetime
    links_checked_at: datetime
    reviewer_id: str
    version: str

    async def current(self, now: datetime) -> bool:
        now = _utc(now)
        reviewed, next_review, links = map(
            _utc,
            (
                self.manually_verified_at,
                self.next_review_at,
                self.links_checked_at,
            ),
        )
        source = urlsplit(self.official_source)
        return (
            self.country_code in {"US", "CA"}
            and bool(self.service_name.strip() and self.purpose.strip() and self.hours.strip())
            and bool(self.contact_methods and all(item.strip() for item in self.contact_methods))
            and bool(self.languages and self.reviewer_id.strip() and self.version.strip())
            and source.scheme == "https"
            and bool(source.hostname)
            and not source.username
            and not source.password
            and reviewed <= now <= reviewed + timedelta(days=35)
            and now < next_review
            and links <= now <= links + timedelta(days=7)
        )


class CrisisRegistry:
    """An empty registry is intentional: historical decision sources are not fresh verification."""

    def __init__(self, resources: tuple[CrisisResource, ...] = (), *, clock: Clock = default_clock):
        self.resources = resources
        self.clock = clock

    async def referral(self, tier: SafetyTier, *, country_code: str | None = None) -> str | None:
        if tier == "ordinary":
            return None
        if tier == "ambiguous":
            return (
                "Are you in immediate danger, or thinking about suicide or serious self-harm now?"
            )
        if tier not in {"explicit", "immediate"}:
            raise ValueError("Unknown safety response tier")
        # Emergency guidance always remains available, including with the wellbeing kill switch.
        base = (
            STATIC_EMERGENCY_REFERRAL
            if tier == "immediate"
            else (
                "Amigo cannot provide crisis care or monitor your safety. "
                "Please contact local crisis "
                "support and a trusted person nearby now. If you are in immediate danger, contact "
                "local emergency services or go to the nearest emergency department."
            )
        )
        for resource in self.resources:
            if country_code == resource.country_code and await resource.current(
                self.clock.utc_now()
            ):
                return (
                    f"{base} {resource.service_name}: {'; '.join(resource.contact_methods)}. "
                    f"{resource.hours}. {resource.official_source}"
                )
        # No stale, unreviewed or geographically inferred contact details are rendered.
        if country_code is None:
            base += " Which country are you in?"
        return base


class WellbeingPolicy:
    """Check on every Turn, before storing sensitive input or calling any model."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        readiness: WellbeingReadiness | None = None,
        registry: CrisisRegistry | None = None,
        clock: Clock = default_clock,
    ):
        self.enabled = enabled
        self.readiness = readiness or WellbeingReadiness()
        self.registry = registry or CrisisRegistry(clock=clock)
        self.clock = clock

    async def check(
        self, participant_id: str, consent: ProcessingConsent | None
    ) -> WellbeingDecision:
        if not self.enabled:
            return WellbeingDecision(False, "disabled", REFLECT_UNAVAILABLE)
        if not await self.readiness.complete():
            return WellbeingDecision(False, "prerequisites_missing", REFLECT_UNAVAILABLE)
        if (
            not isinstance(consent, ProcessingConsent)
            or not isinstance(consent.acknowledged_at, datetime)
            or consent.participant_id != participant_id
            or consent.policy_version != REFLECT_CONSENT_VERSION
            or consent.withdrawn_at is not None
            or _utc(consent.acknowledged_at) > _utc(self.clock.utc_now())
        ):
            return WellbeingDecision(False, "consent_required", REFLECT_CONSENT_NOTICE)
        return WellbeingDecision(True, "allowed", None)

    async def referral(self, tier: SafetyTier, *, country_code: str | None = None) -> str | None:
        """Always callable, including when processing is disabled or model generation fails."""
        return await self.registry.referral(tier, country_code=country_code)
