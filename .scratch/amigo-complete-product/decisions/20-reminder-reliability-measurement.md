# Define Reminder Reliability Measurement Semantics

Parent: [Amigo Complete Product](../MAP.md)
Status: closed
Label: `wayfinder:grilling`
Type: HITL / grilling
Severity: `severity:high`
Owner: Codex
Blocked by: [Resolve the Task and Reminder Lifecycle](05-task-reminder-lifecycle.md), [Capture the Render and Supabase Runtime Baseline](07-runtime-baseline.md)

## Question

What makes a Reminder eligible for reliability measurement, what constitutes healthy-provider
conditions, which timestamps define delivery and lateness, and how should cancelled, deferred,
retried, failed, and small-sample outcomes enter gate calculations?

## Comments

### 2026-08-29 — Eligible Reminder population

- The measurement unit is one immutable Reminder occurrence (one Reminder row), not one send
  attempt.
- A Reminder is eligible after it is validly confirmed for a future instant and remains active
  when its scheduled instant arrives.
- Report Beta Runtime and staging synthetic populations separately.
- Amigo runtime outages remain in the denominator; internal downtime cannot make a Reminder
  ineligible.
- Exclude a Reminder cancelled because its Task was completed, skipped, cancelled, explicitly
  rescheduled, muted, or deleted before its scheduled instant only when that earlier transition is
  durably timestamped. Without proof, it remains eligible.
- Rescheduling cancels the old occurrence and creates a new one. Later preserves the already-
  delivered occurrence's outcome and creates a separately measured replacement.
- Retries are attempts within one occurrence and produce one final reliability outcome.
- Invalid past-time scheduling is a separate product-correctness failure and cannot be hidden in
  delivery exclusions.

### 2026-08-29 — Timestamp and metric model

- A Reminder occurrence records `confirmed_at`, canonical UTC `scheduled_for`,
  `first_claimed_at`, `provider_accepted_at`, `terminal_at`, participant `acknowledged_at`, and,
  where applicable, `cancelled_at` plus cancellation reason.
- Each delivery attempt records attempt number, start/end timestamps, result, provider identifier,
  idempotency key, normalized failure class, and next retry time.
- Reminder Delivery Success means provider acceptance within 15 minutes of `scheduled_for`; it is
  not a claim of device receipt or reading.
- Reminder Lateness is `provider_accepted_at - scheduled_for`; Scheduler Lag is
  `first_claimed_at - scheduled_for`; Provider Latency is the successful attempt's
  `provider_accepted_at - attempt_started_at`.
- Participant acknowledgement is an engagement metric, not reliability proof.
- Use durable UTC server/database timestamps and convert only for presentation.
- A Messaging Channel without acceptance evidence cannot count an occurrence as successful.
- A successful channel API call must record provider acceptance even when no editable provider
  Message identifier is returned.

### 2026-08-29 — Healthy-provider attribution

- Publish End-to-End Reliability across every Eligible Reminder and Healthy-Provider Reliability,
  which excludes only Reminders due inside a predeclared, evidenced external-provider incident.
- Declare an external incident only from an official provider incident or at least three
  consecutive automated provider-probe failures across five minutes while Amigo app and database
  health checks pass.
- Record evidence, start/end times, affected operations, and owner. Close after official
  resolution or two consecutive successful probes.
- Authentication/configuration errors, invalid recipient identifiers, exhausted quota, malformed
  requests, Amigo-caused rate limits, and internal network/configuration failures are never
  provider exclusions. An isolated timeout remains in both views.
- Do not create incident windows retroactively after inspecting Reminder outcomes.
- Keep excluded counts and participant impact visible beside Healthy-Provider Reliability.
- Use the healthy-provider view for the formal release threshold, while material end-to-end
  failure still requires investigation and disclosure.

### 2026-08-29 — Retry and terminal outcomes

- Permit at most three total attempts inside the 15-minute delivery window: the initial attempt,
  then approximately 10 and 60 seconds later, while honoring a provider Retry-After value that
  fits the window.
- Retry only provider-classified explicit non-acceptance that is safe to retry. When a request may
  have been accepted but the response is ambiguous and the provider gives no idempotent-send
  guarantee, do not automatically retry; mark `failed` with `ambiguous_provider_outcome` and alert.
- Never return a failed attempt silently to `pending`; preserve attempts and next action.
- Stop initiating sends at 15 minutes. No attempt because Amigo was late becomes `missed`; exhausted
  explicit rejection and ambiguous outcomes become `failed`; acceptance from an already in-flight
  request after the window remains factually `sent` but is outside-window and unsuccessful.
- Acceptance before `scheduled_for`, duplicate acceptance, or sending after a recorded cancellation
  is a hard product-correctness failure and cannot count as success.
- Done, Skip, or Later changes engagement/lifecycle state without rewriting the delivery outcome.

### 2026-08-29 — Sample and calculation rules

- Publish numerator, denominator, exclusion count/reasons, percentage, p50, p95, maximum lateness,
  failure causes, retry counts, and provider-incident impact. Show End-to-End and Healthy-Provider
  views side by side.
- Use nearest-rank percentiles. With fewer than 20 successful observations, do not claim p95;
  label it Insufficient Evidence and show every value plus the maximum.
- Pre-beta staging requires at least 100 Eligible Reminders across three runs including the
  Representative Beta Burst, at least 99% in-window acceptance, p95 lateness no more than 10
  seconds, maximum no more than 30 seconds, and zero duplicate/cross-account delivery.
- Provisional live-beta evidence requires at least 50 Eligible Reminders from at least five
  participants across seven days, at least 99% Healthy-Provider Reliability, and p95 lateness under
  five minutes.
- Customer Readiness requires at least 100 Eligible Reminders from at least five participants
  across 14 days with the same 99% and p95 thresholds.
- Insufficient observations produce Insufficient Evidence, never a pass. Require cumulative and
  trailing-seven-day results to pass when the trailing window has at least 20 Reminders.
- No participant may experience more than one Amigo-attributable failure in a gate window; review
  every failure. Duplicate or cross-account delivery is a hard failure regardless of percentages.

### 2026-08-29 — Instrumentation and resolution

- Add durable occurrence timestamps and an immutable attempt ledger through a human-reviewed
  migration; mirror interface changes across MemoryStore, InMemoryStore, and FakeStore.
- Historical rows without required events are Unmeasurable and cannot be reconstructed from
  mutable status.
- Reconcile at least once per minute: mark active occurrences beyond 15 minutes `missed`, detect
  stuck `sending`, validate terminal timestamps, find multiple provider acceptances, and find due
  occurrences with no attempt.
- Alert immediately for missed/failed Reminders, duplicates, cross-account delivery, sends after
  cancellation, and inconsistent terminal state. Warn when a due Reminder remains unclaimed for
  60 seconds or scheduler heartbeat is absent for three minutes.
- Run one separately reported hourly production synthetic Reminder to a dedicated operator
  endpoint. Never mix it with participant results.
- Provide content-free drill-down for current day, trailing seven days, and cumulative gate window.
  Retain detailed reliability metadata for 90 days and aggregates for 12 months.
- Test restart/redeploy, retry safety, ambiguous timeout, rejection, database failure, concurrent
  claim, cancellation race, late in-flight acceptance, and clock/timezone boundaries.
- Deploy and verify measurement before the first external invitation.

The current scheduler does not satisfy this contract: it lacks the required event timestamps and
attempt ledger and resets send failures to `pending`. Those are implementation gaps, not historical
evidence.
