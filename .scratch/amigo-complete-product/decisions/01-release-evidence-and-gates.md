# Define Release Evidence and Gate Thresholds

Parent: [Amigo Complete Product](../MAP.md)
Status: closed
Label: `wayfinder:grilling`
Type: HITL / grilling
Severity: `severity:high`
Owner: unassigned
Blocked by: none

## Question

What exact evidence, thresholds, owners, and stop conditions distinguish Internal Preflight,
External Invitation Beta, Customer Readiness, and each post-beta ship-or-do-not-build gate?

## Comments

### Resolution — 2026-08-29

#### Gate policy

- Critical findings cannot be waived.
- A High finding cannot be waived for the release gate where it is required.
- A Medium finding may receive a time-limited written waiver with owner, reason, mitigation,
  expiry date, and follow-up ticket.
- Low findings do not block release unless explicitly promoted.
- Cross-user access, duplicate or misdirected Reminders, or an open Critical security, privacy,
  or safety incident stops enrollment automatically.

#### Internal Preflight

Gate A requires green backend/frontend CI; clean migration setup including pairing/RLS; passing
two-user isolation and fail-closed configuration tests; idempotent Telegram replay; three
consecutive staging runs of Dashboard Account → Pairing → Task → Reminder → Done → dashboard
synchronization; clarification of ambiguous time; one verified Render webhook/scheduler owner;
restart recovery; observable errors, delivery, and lateness; and no open Critical or Gate-A High
finding. Evidence is dated and tied to the tested release.

#### External Invitation Beta opening

Gate B requires Gate A to remain green; four of five first-time usability participants to reach a
delivered test Reminder without founder intervention; median Activation under five minutes;
tested founder-operated export and deletion; published privacy, retention, non-clinical limits,
known limitations, and support instructions; verified invite access, quotas, rate limits, cost
alarm, and kill switch; passing expanded model evaluation and representative Render burst;
detection of an injected Reminder failure; rehearsed restore and rollback; a documented Target
Segment, recruitment source, support owner, review cadence, stop conditions, and feedback triage;
and no open Critical or Gate-B High finding. D1/D7 and real-cohort reliability do not block the
first invitation because that evidence does not yet exist.

#### Beta stop and resume

Pause new invitations for cross-user access/mutation; duplicate or misdirected Reminder; incorrect
Pairing; failed documented deletion; a Critical safety event or non-clinical-boundary violation;
an exposed secret or pairing vulnerability; delivery below 95% over the latest 20 eligible
Reminders in healthy-provider conditions; p95 lateness over five minutes for the latest 20
delivered Reminders; emergency spend threshold breach; or unavailable monitoring, scheduler
heartbeat, or kill switch. Provider-wide outages pause onboarding and experiments but are tracked
separately from Amigo-caused reliability. Resume only after a fix, attached regression evidence,
and explicit founder approval.

#### Customer Readiness

Gate C requires at least five Target Segment participants to complete D7; at least 80% onboarding,
70% Activation, 99% healthy-provider Reminder delivery, zero known duplicate/cross-user
Reminders, p95 lateness under five minutes, and at least 40% D7 return as an early signal; three
documented participant outcomes; passing self-service export/deletion; proportionate professional
review of privacy, terms, non-clinical boundaries, and US/Canada-facing copy; a published offer and
measured cost; three consecutive clean-account demos plus sanitized assets and fallback recording;
passing mobile/accessibility checks; and no open Critical or Gate-C High finding. Gate C means
credible customer presentation and careful expansion, not proven product-market fit.

#### Roadmap capability gates

Every roadmap capability passes Discovery, Prototype, Limited release, and Ship gates. Discovery
requires a concrete problem demonstrated or independently requested by at least three
participants and not adequately solved today. Prototype requires a narrow contract covering data,
cost, failures, controls, four-of-five moderated comprehension/value, and no unresolved Critical
risk. Limited release requires opt-in, kill switch, evaluation, isolation, export/deletion,
rollback, sustainable cost/support, and no Core Loop degradation. Ship requires its outcome
threshold plus acceptable corrections, disengagement, harms, and cost. Weak demand, unsafe
behavior, unsustainable cost, or conflict with the non-clinical boundary closes the branch as
do-not-build; reconsideration requires new evidence.

#### Ownership

The founder is accountable release owner, enrollment authority, operations owner, and beta
support owner. Implementers produce evidence but do not approve their own Critical
security/privacy work. Independent review is required for migrations, tenant isolation, pairing
security, deletion, sensitive-data handling, and non-clinical safety behavior. If appropriate
review is unavailable, the affected high-risk function remains disabled. Every item records owner,
date, tested release/environment, and evidence link.

#### Evidence validity

CI, migration, security, model, and staging evidence identifies the exact commit/release. The
staging Core Loop reruns for every production release. Model evidence is invalidated by changes to
the model, prompt, Tool schema, time semantics, or Turn Context. Pairing/RLS evidence is
invalidated by auth, policy, migration, or ownership-query changes. Burst evidence reruns after
infrastructure, database client, concurrency, scheduler, or Render-plan changes and at least every
90 days during enrollment. Restore evidence reruns at least every 90 days. Material onboarding
changes invalidate usability evidence. Data collection, processor, Target Segment, or market-claim
changes reopen the relevant privacy, retention, and non-clinical review. Invalid evidence reopens
the affected gate.
