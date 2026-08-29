# Wayfinder Map: Amigo Complete Product

Label: `wayfinder:map`
Status: open
Owner: unassigned

## Destination

Reach a production-ready, evidence-gated Amigo: a reliable non-clinical accountability companion
with transparent memory, user-controlled adaptive modes, and validated expansion across Telegram,
WhatsApp, voice, and mobile. Every roadmap capability receives a ship-or-do-not-build decision;
anything shipped meets its demand, safety, cost, privacy, and reliability gate.

## Notes

- Source plan: [`docs/pre-launch-implementation-plan.md`](../../docs/pre-launch-implementation-plan.md)
- Source assessment: [`docs/pre-launch-gap-analysis.md`](../../docs/pre-launch-gap-analysis.md)
- Runtime vocabulary: [`CONTEXT.md`](../../CONTEXT.md)
- Launch vocabulary: [`UBIQUITOUS_LANGUAGE.md`](../../UBIQUITOUS_LANGUAGE.md)
- Read relevant ADRs before resolving architecture decisions.
- Use `grill-me` plus domain modeling for `wayfinder:grilling` tickets.
- Use `prototype` for `wayfinder:prototype` tickets.
- Initial **Target Segment**: English-speaking adults 18+ in the United States and Canada who
  struggle with everyday task follow-through and abandon conventional task apps.
- Do not hard geo-block the product, but do not claim evaluated support for an unreviewed market.
- Keep beta controls proportionate to a small invitation cohort.
- Amigo is non-clinical. It may offer supportive reflection, CBT-informed exercises, mood
  journaling, and crisis-resource referral; it does not diagnose, provide treatment or therapy,
  or promise monitored crisis response.
- Memory, modes, wellbeing, and channel expansion remain in scope but are evidence-gated. A
  documented “do not build” decision can successfully close a branch.

## Decisions so far

<!-- Closed decision tickets are indexed here by name with a one-line gist. -->

- [Define Release Evidence and Gate Thresholds](decisions/01-release-evidence-and-gates.md):
  Adopted non-waivable Critical/required-High gates, explicit A/B/C evidence, beta stop/resume
  rules, evidence-gated roadmap branches, named ownership, and evidence invalidation rules.
- [Lock the Beta Promise and Capability Exclusions](decisions/02-beta-promise-and-exclusions.md):
  Defined the Task-to-Telegram-Reminder promise, shipped beta capability contract, explicit
  exclusions, AI-accountability-companion category, dashboard-first explanation, and narrow
  “reaches out first” language.
- [Choose the Beta Offer and Support Contract](decisions/03-beta-offer-and-support.md): Adopted a
  free 30-day invitation beta with bounded usage, asynchronous founder support, explicit
  participant expectations, voluntary withdrawal, and documented suspension/termination terms.
- [Define the Proportionate Beta Privacy and Retention Contract](decisions/04-beta-privacy-retention.md):
  Approved the minimized data inventory and purposes, short retention schedule, named processors,
  versioned consent, founder-operated export/deletion, correction/support path, and incident
  communication for the invitation beta.
- [Resolve the Task and Reminder Lifecycle](decisions/05-task-reminder-lifecycle.md): Adopted
  due-date-based planning and Inbox semantics, explicit time clarification and quiet hours, one
  Later/carry-over policy, immutable Reminder transitions, and terminal Task outcomes.
- [Choose the Cross-Surface State Contract](decisions/06-cross-surface-state-contract.md): Adopted
  authenticated shared commands, atomic database transitions with a durable scheduler outbox,
  database-authoritative reconciliation, and one versioned dashboard snapshot.
- [Capture the Render and Supabase Runtime Baseline](decisions/07-runtime-baseline.md): Confirmed a
  sleeping single Render Free instance, cross-region Supabase NANO database, ambient resource and
  health observations, and that core latency/lateness metrics are currently uninstrumented.
- [Choose the Runtime I/O and Capacity Strategy](decisions/08-runtime-io-and-capacity.md): Kept the
  free sleeping topology for development only; adopted native async Supabase I/O, bounded beta
  concurrency and prioritized Reminder work, one always-on US-West Render owner, and an exact
  representative-burst gate for the 5–10-person cohort.
- [Define the Model Evaluation Contract](decisions/09-model-evaluation-contract.md): Adopted
  non-waivable model hard invariants, exact Gate A/Gate B case inventories and category
  thresholds, English beta output with code-mixed comprehension coverage, non-clinical safety and
  Tool authorization rules, and reproducible versioned evaluation evidence.
- [Approve the Dashboard-First Activation Journey](decisions/10-dashboard-activation-prototype.md):
  Selected a focused dashboard-led journey, cross-surface Telegram previews only at handoffs, and
  a resumable checklist for recovery; Activation ends only after the guided test Reminder is
  delivered, resolved in Telegram, and reflected back on the dashboard.
- [Choose the Invitation Cohort and Recruitment Protocol](decisions/11-cohort-and-recruitment.md):
  Adopted a separate compensated usability panel, an eight-person two-wave cohort plus waitlist,
  arm's-length targeted recruitment and non-clinical use screening, standardized baseline/D7
  research, explicit Intervention Log accounting, and daily/weekly enrollment controls.
- [Define Customer Readiness and the Sustainable Offer](decisions/12-customer-readiness-and-pricing.md):
  Selected a hosted-first model and revisable US$9 monthly Pricing Hypothesis, requiring measured
  quality/value, bounded support and 25% variable cost, and two actual paid continuations before
  commercial validation; defined explicit iterate, pause, reposition, and stop branches.
- [Choose the Memory and Memory Inspector Trust Contract](decisions/13-memory-trust-contract.md):
  Adopted demand-gated, explicit-first Memory with prohibited sensitive categories, temporal
  validity and correction, bounded non-authorizing retrieval, separate learning/use pauses, a
  complete Inspector/export/deletion contract, and automated, usability, and opt-in trial gates.
- [Choose the Mode and Adaptive Coaching Contract](decisions/14-mode-and-adaptation-contract.md):
  Kept Daily as the default workspace; defined explicit, temporary, deny-by-default specialized
  Modes, participant-confirmed Interaction Style, bounded Coach and Reflect contracts, evidence-led
  sequencing, and independent usability and opt-in release gates.
- [Define the Non-Clinical Wellbeing and Crisis-Referral Contract](decisions/15-nonclinical-wellbeing-contract.md):
  Approved a bounded exercise and Mood Entry scope, explicit sensitive-data consent and retention,
  a limitation-first response ladder, verified U.S./Canada referral registry, non-monitoring safety
  telemetry and kill switch, and strict automated, human-review, usability, and trial gates.
- [Choose the Surface Expansion Portfolio and Priority](decisions/16-channel-expansion-priority.md):
  Separated Messaging Channels, Interaction Modalities, and Client Surfaces; chose No Expansion Yet,
  defined observed-demand gates, one canonical identity and Primary Messaging Channel contract,
  evidence collection, single-expansion sequencing, and a common parity/reliability release gate.
- [Define Reminder Reliability Measurement Semantics](decisions/20-reminder-reliability-measurement.md):
  Defined the Eligible Reminder population, provider-acceptance timestamps and lateness metrics,
  two-view provider attribution, duplicate-safe retry outcomes, staging/live sample thresholds,
  durable attempt instrumentation, reconciliation, alerts, and synthetic measurement.
- [Choose the Project Source License and Contribution Contract](decisions/21-project-license.md):
  Selected repository-wide AGPL-3.0 for Amigo's original work, DCO 1.1 sign-off without a CLA,
  and private GitHub vulnerability reporting with bounded response targets and coordinated
  disclosure; supported self-hosting remains a separate product promise.

## Not yet specified

- Which durable-memory storage and retrieval technology fits the approved Memory contract.
- [Which narrow recommendation domain and data sources justify Recommender Mode?](decisions/22-recommender-domain.md)
- [Can evidence ever justify automatic mode routing or unconfirmed adaptation?](decisions/23-automatic-routing-and-adaptation.md)
- [When should verified Crisis Referral coverage expand beyond the U.S. and Canada?](decisions/24-international-crisis-referrals.md)
- [Which WhatsApp product and integration contract should govern an approved expansion?](decisions/17-whatsapp-contract.md)
- [Should voice use asynchronous messages, live conversation, or neither?](decisions/18-voice-contract.md)
- [Does validated mobile demand require responsive web, a PWA, native mobile, or no separate app?](decisions/19-mobile-contract.md)
- Detailed implementation slices for post-beta capabilities; these graduate only after their
  governing decision tickets close.

## Out of scope

- Autonomous or human-presented diagnosis, clinical treatment, psychotherapy, or medical advice.
- A monitored crisis service or any promise that Amigo is continuously watched by responders.
- Shipping a roadmap capability solely because it appeared in an early vision document.
- Hard geographic blocking as the default expansion mechanism.
