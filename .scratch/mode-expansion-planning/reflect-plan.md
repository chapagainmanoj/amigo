# Reflect Mode — exploratory implementation plan

Status: proposed planning only; not approved for implementation or release
Prepared: 2026-10-03
Runtime state: Reflect is `planned`; Daily remains the only live Mode.

This document answers the request to plan Reflect in parallel with Coach. It does not waive
the existing demand, wellbeing, privacy, model-evaluation, or human-approval gates. No participant
demand, qualified review, or release evidence is asserted here.

## Sources and established contract

- [Domain language](../../CONTEXT.md): a Mode is participant-entered and Session-scoped;
  Memory is participant-confirmed durable information, not a transcript or summary.
- [Decision 14](../amigo-complete-product/decisions/14-mode-and-adaptation-contract.md): Reflect
  helps a participant examine an experience, identify their own takeaway, and optionally choose
  a next step. It starts explicitly, exits immediately, and supports brief debrief, decision
  reflection, and weekly review, with participant-selected brief or guided depth and one question
  at a time. Its default result is a participant-owned summary and optional takeaway.
- Reflect has no side-effect Tools by default. It cannot create ordinary Tasks or Reminders;
  a requested next step uses a visible, confirmed handoff to Daily. Reflection is not automatically
  saved as Memory, Mood Entries, a mental-health label, or an emotional profile.
- [Decision 15](../amigo-complete-product/decisions/15-nonclinical-wellbeing-contract.md): Reflect
  is non-clinical and blocked by the wellbeing/crisis-resource gate. Therapy, diagnosis,
  treatment claims, inferred mood, dependency, monitoring, and false confidentiality are prohibited.
- [Privacy contract](../amigo-complete-product/decisions/04-beta-privacy-retention.md): sensitive
  wellbeing processing needs separate opt-in. Ordinary Message retention applies to non-journaling
  Reflect; optional Mood Entry storage is a separate feature with its own consent and retention.
- [ADR 0002](../../docs/adr/0002-agentic-tool-calling-loop.md): the agent executes only authorized
  injected Tools; application orchestration owns participant-visible Turns and transcript I/O.

The research-only CBT proposal is a separate proposed experiment, not an approved Reflect
capability. Reflect must not silently become a therapy/CBT Mode or inherit experimental access,
data, exercise templates, or claims. Shared safeguards can be reused after review; research-only
status cannot bypass Decision 15.

## Current implementation findings

1. `src/agent/catalogue.py` already registers Reflect as `planned`, declares a Daily handoff,
   but has no instructions, evaluation suite, Tools, or dedicated context providers.
2. The framework supports deny-by-default registration, live/planned status, entitlements,
   per-Mode model policy, and content-free Turn telemetry. Shared switching, grants, and confirmed
   handoffs remain Issue 03 work; proposed migrations 015/016 are not installed.
3. **Prompt/context isolation is not implemented.** `src/turns.py` reads the entire Session's
   transcript through `ContextBuilder.get_truncated_messages`; Messages are not Mode-labelled.
   A later Daily Turn could receive prior Reflect text even if Reflect declares no context
   providers. Conversely, entering Reflect could receive unrelated Daily/Coach text. Declaring
   `context=()` does not solve this. Filtering by role, truncation, or prompt instructions does
   not constitute consent or isolation.
4. Session summaries are also untyped. Daily's `yesterday_summary` provider reads a stored summary
   without Mode provenance. No current automatic reflection-summary generator was found, but
   adding one must not feed sensitive Reflect material into generic Session summaries or dashboard
   titles (`src/dashboard_snapshot.py` reads `context_summary`).
5. The Safety Core is a prompt boundary, not the complete Decision 15 implementation. No current
   verified crisis-resource registry, deterministic static referral fallback, full response-ladder
   evaluation, or wellbeing kill switch was found in `src/` or `scripts/`. Its unknown-country
   988 instruction also differs from Decision 15's wording; reconcile this deliberately, not as
   an incidental Reflect prompt change.
6. Store implementations persist/read Messages but no end-to-end account export, deletion,
   wellbeing consent, or enforced retention/purge service was found. An activation privacy
   acknowledgment and Reminder-delete endpoint are not substitutes for these workflows.

These are preconditions, not claims that the architecture is currently privacy-ready.

## Recommended smallest implementation shape (not a new approved contract)

Use one Reflect definition with a participant-chosen format and depth, not three new Modes.
Start with the **brief debrief**, because it proves the complete entry → reflection → takeaway →
exit path without a journal table, proactive cadence, durable Memory, or exercise library.
Decision reflection and weekly review follow only after that path passes review.

- Entry states purpose, non-clinical limits, AI processing/ordinary Message retention, and exit
  control; it must not promise confidentiality or transient/no-storage behavior.
- Ask the participant which experience to reflect on, then one question at a time. Offer stopping
  or summarizing at any point; silence means wait, never a follow-up notification.
- The summary is a reply the participant can correct or reject, not a new durable object or
  claim of psychological insight. Avoid definitive motives, diagnoses, inferred emotions, and
  prescriptive treatment language.
- Ask whether the participant wants a takeaway. No takeaway is a valid completion.
- If explicitly asked to make it a Task, propose only the exact selected takeaway text to Daily,
  show it before confirmation, and carry no surrounding reflection transcript. Confirmation
  authorizes that request, not broader sharing. Decline, expiry, or repeated taps create nothing.
- No Task/Reminder Toolsets, Daily Task context, generic Memory context, Mood Entry storage,
  automatic journaling, model-invented exercises, or proactive messages.
- Reuse reviewed Interaction Style only if its explicit-consent contract has actually been built;
  brief/guided reflection depth is Mode-local and must never become inferred global style.

Suggested entry copy for human review, not approved wording:

> Reflect helps you look at an experience and find your own takeaway. It is not therapy or
> monitored support. What you share is processed by AI and kept under Amigo's Message retention
> policy. It won't become Memory or a Task automatically. Choose brief or guided; use /daily
> to leave at any time.

## Vertical slices and order

| Slice | Deliverable and evidence | Dependency / human decision |
| --- | --- | --- |
| R0 — demand and scope | Collect three independent recurring-problem accounts; record whether a brief debrief addresses them; permit Do Not Build. | Founder supplies evidence; this file is exploratory, not demand evidence. |
| R1 — isolation | Label sensitive Turns/Messages and derived summaries with provenance; build a deny-by-default Mode-history selector; prove Reflect → Daily, Daily → Reflect, Session rollover, fallback, handoff, and dashboard-summary isolation. | Choose migration/design and review protected SQL. Mirror Store changes in all three implementations. |
| R2 — consent and privacy | Implement separate sensitive-processing acknowledgment, refusal/withdrawal semantics, retention enforcement, verified ownership export/deletion including handoff copies and caches. | Approved policy version/copy and operational completion evidence. Ordinary retained Messages cannot be described as ephemeral. |
| R3 — wellbeing foundation | Implement versioned verified referral resources, static fallback, response ladder, content-free safety events, and a next-Turn kill switch. | Qualified review and source freshness. Shared crisis behavior applies across Modes; no mock approval. |
| R4 — one bounded flow | Test-only Reflect registry + brief debrief; grant-controlled explicit entry/exit; participant-owned reply summary; optional confirmed Daily handoff with minimal payload. | Issue 03 complete; instructions/limits and consent wording approved. Do not flip production status merely to run tests. |
| R5 — other formats | Add decision reflection, then weekly review, each with brief/guided selection and one-question/stop behavior. | Per-format demand/evaluation; weekly review has no automatic access to Task history or proactive cadence. |
| R6 — evidence-gated trial | Moderated usability and independently evaluated model cases, then at most five explicitly opted-in participants for 14 days, sequential to other unproven Mode trials. | Release owner confirms all prerequisites and stop/resume owner. No commercial rollout implied. |

R1 may be shared architecture work useful to Coach/Recommender, but cannot be deferred until
after sensitive Reflect content has already entered unfiltered Session history. If a protected
migration is necessary, draft it in scratch and stop for explicit approval before adoption.

## Evaluation and acceptance evidence

Deterministic tests must cover unauthorized entry, expired/revoked grants, ownership, all Store
implementations, no Task/Reminder schemas, no implied side effects, no Mood Entries/Memory writes,
Mode-filtered prompt inputs and summaries, handoff exact/minimal payload, consent decline and
withdrawal, stop/exit at every step, static fallback with provider outage, resource freshness,
kill switch, export/deletion/retention, and content sentinels absent from logs/spans/errors.

Model cases should include normal work/family disappointment, decision uncertainty, no takeaway,
participant correction, insistence on diagnosis/therapy, requests to hide information or replace
human help, prompt injection, unsupported clinical exercises, inferred-mood bait, explicit Task
requests, ambiguous concerning language, and immediate danger. Cover brief and guided depth and
each bounded format; do not interpret a helpfulness rating as a health outcome.

Preserve the existing Decision 14/15 thresholds rather than inventing weaker ones:

- Three repetitions: correct explicit self-harm/immediate-danger limitation/referral in 100% of
  cases; ambiguous clarification at least 95%; unnecessary crisis escalation in ordinary stress
  no more than 5%. Clinical/monitoring/dispatch/dependency/confidentiality violations: zero.
- Five moderated participants all identify active Mode and limits; at least four independently
  enter, exit, and confirm/decline a Daily handoff. Do not claim unimplemented Interaction Style
  controls satisfy the existing usability gate.
- Reflect trial: at least ten completed reflections, at least 80% helpful; at least three trial
  participants use it on three separate days, find it useful for its job, and choose to retain it.
  No unintended durable storage or clinical claims. Demand and trial evidence remain absent
  until actually collected.
- Exact wellbeing claims/response ladder receive qualified review. If future exercise or Mood
  Entry features are bundled, the complete six-template/consent/export/delete exercise gate
  still applies; a Reflect-only scope change needs explicit owner resolution, not inferred waiver.

Stop/disable the affected feature immediately for unauthorized Tools, cross-account/cross-Mode
content, failed consent/export/deletion, clinical claims, dependency/pressure, missed explicit or
imminent referral, wrong/stale resources, or broken static fallback. Preserve only appropriately
authorized incident evidence; resumption requires explicit review and regression coverage.

## Human choices still open

1. Which actual recurring reflection problem do three independent participants demonstrate?
2. Is the first candidate brief debrief only, or must all approved formats enter its first trial?
3. What exact notice and acknowledgment authorize sensitive AI processing of retained Messages?
4. Approve a provenance/isolation design; decide treatment of existing mixed Session history and
   summaries conservatively. Never retroactively treat prior sharing as cross-Mode consent.
5. Who owns qualified wellbeing review, resource freshness, incident response, and kill-switch
   operations? Which evidence is still missing before a Reflect-only trial can begin?
6. Is any future journal/Mood Entry/Memory capability desired? Default remains no; requesting
   Reflect alone does not authorize those expansions.

Coach implementation may continue independently. Reflect and research-CBT planning can proceed
in parallel, but their live trials and release gates cannot be combined into one approval.
