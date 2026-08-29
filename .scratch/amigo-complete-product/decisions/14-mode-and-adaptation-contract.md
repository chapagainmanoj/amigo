# Choose the Mode and Adaptive Coaching Contract

Parent: [Amigo Complete Product](../MAP.md)
Status: closed
Label: `wayfinder:grilling`
Type: HITL / grilling
Severity: `severity:high`
Owner: Codex
Blocked by: [Choose the Memory and Memory Inspector Trust Contract](13-memory-trust-contract.md)

## Question

Which user needs justify Daily, Recommender, Coach, and Reflect modes, how should users select or
override them, and which inspectable evidence can safely authorize gradual coaching adaptation?

## Comments

### 2026-08-29 — Mode definition and selection

- Daily is the default core workspace, not a specialized persona.
- Recommender, Coach, and Reflect are temporary, participant-entered Modes with separate
  capability contracts. Use **Recommender Mode** as the canonical roadmap term; the current
  dashboard's “Discover mode” wording is inconsistent and must not become a second domain term.
- At most one specialized Mode is active within a Session.
- Entering a Mode does not hide or mutate existing Tasks or Reminders.
- A participant enters a Mode through an enabled dashboard control or explicit conversational
  request and can switch or exit immediately.
- A new Session starts in Daily. A longer-lived coaching program may persist, but Coach Mode does
  not remain silently active across Sessions.
- Automatic mode switching is excluded from the initial release.
- Until a Mode passes its own release gate, its dashboard control is disabled, labelled Planned,
  and cannot imply an active or previewable shipped capability.

### 2026-08-29 — User jobs and demand gates

- Daily serves: “Help me decide, remember, and follow through on what I intend to do today.” It
  remains the Core Loop.
- Coach serves: “Help me pursue one user-chosen goal or habit through a plan, bounded check-in
  cadence, progress review, and adjustment.” It is neither general life advice nor expert
  coaching.
- Reflect serves: “Help me privately examine an experience, identify my own takeaway, and
  optionally choose a next step.” It is non-clinical, does not diagnose or treat mood, and does
  not automatically create Tasks.
- Recommender serves: “Help me choose among options in one approved recommendation domain using
  stated preferences and explainable trade-offs.” A generic all-purpose recommender is excluded.
- Each specialized Mode requires at least three independent participants to demonstrate its
  recurring problem before design begins. Validate each Mode independently; evidence for one
  cannot justify another.
- Recommender remains blocked until its first narrow domain and data source receive a separate
  approval.

### 2026-08-29 — Mode capability and data boundaries

- Enforce a deny-by-default registered contract for every Mode in deterministic code. The
  contract declares purpose, allowed Tools, allowed data, retention, safety policy, UI surfaces,
  and evaluation suite.
- Daily may use Task and Reminder Tools plus eligible general Memory.
- Coach may manage a participant-approved coaching program, goal, cadence, check-ins, and progress;
  it cannot create ordinary Tasks or Reminders without a confirmed handoff to Daily.
- Reflect has no side-effect Tools by default. Reflection entries remain separate from Memory
  unless the participant explicitly saves an eligible Memory.
- Recommender may read approved domain preferences and sourced option data, but cannot purchase,
  book, contact, or transact.
- An ordinary Task or Reminder request inside a specialized Mode offers a visible, confirmed
  handoff to Daily.
- Mode-specific data cannot become general Memory or flow into another Mode without explicit
  consent.
- Runtime checks enforce Tool access, data access, and cross-Mode transitions. Both Telegram and
  the dashboard display the active Mode.

### 2026-08-29 — Participant-confirmed adaptation

- Interaction Style is a participant-controlled setting, not Memory, Coach Mode, or an inferred
  personality profile.
- Initial dimensions are warmth (`neutral` or `warm`), directiveness (`gentle`, `balanced`, or
  `direct`), verbosity (`concise`, `balanced`, or `detailed`), and challenge (`supportive`,
  `balanced`, or `challenging`).
- An explicit participant request changes a setting immediately.
- Amigo may propose one change only after the same preference signal appears across at least three
  Sessions on at least two days. The participant must confirm; silent automatic changes are
  excluded from the initial release.
- Sentiment, assumed mood, diagnosis, demographics, missed Tasks, silence, and response speed
  cannot alter Interaction Style.
- Every proposal explains its evidence. Accepted changes expose history, reset, and undo.
- Safety and non-clinical response rules override style preferences.
- Reflect-specific emotional depth is selected inside Reflect Mode and is not inferred as a global
  style preference.

### 2026-08-29 — Coaching Program contract

- Coach Mode v1 supports at most one Coaching Program at a time, centered on one
  participant-chosen goal or habit and a participant-written measure of success.
- A Coaching Program lasts 14 days by default and extends only through explicit participant
  choice. Its lifecycle is `draft`, `active`, `paused`, `completed`, or `stopped`.
- The participant selects check-in days and time. Proactive coaching is capped at one Message per
  day and remains subject to quiet hours and the shared anti-nag budget.
- Progress is participant-reported; Amigo does not claim objective improvement without evidence.
- One missed check-in permits at most one gentle follow-up, after which Amigo waits for the
  participant.
- A weekly review covers progress, obstacles, and an explicit continue, adjust, pause, or stop
  choice.
- Pause and Stop remain immediately available. Do not use guilt, streak-loss pressure, dependency
  language, or expert-coaching claims.
- Ordinary Tasks and Reminders remain Daily capabilities reached through a confirmed handoff.

### 2026-08-29 — Reflect Mode boundary

- Reflect begins only through explicit participant selection and can be exited immediately.
- Initial bounded formats are a brief debrief, decision reflection, and weekly review. The
  participant chooses brief or guided depth, and Amigo asks one question at a time.
- The default result is a participant-owned summary and optional takeaway.
- Reflection never becomes durable Memory automatically and creates no mood score, mental-health
  label, diagnosis, emotional profile, or background sentiment history.
- Turning a takeaway into a Task requires the confirmed handoff to Daily.
- Reflection remains under existing Message retention unless the participant separately opts into
  future journaling governed by the Milestone 9 contract.
- Reflect cannot ship before the non-clinical wellbeing and crisis-resource gate is approved.
- Reflect avoids dependency language, confidentiality claims beyond the published privacy policy,
  and any therapy or treatment claim.

### 2026-08-29 — Sequencing

1. Daily remains the only shipped experience through the Core Loop external beta.
2. Coach is the first specialized-Mode candidate because its user job is closest to Amigo's
   accountability promise.
3. Reflect remains blocked by the separate non-clinical wellbeing contract.
4. Recommender remains dormant until participant evidence identifies one narrow domain and an
   approved data source.
5. Build shared Mode infrastructure only after the first specialized Mode passes its demand gate.
6. Trial each Mode separately behind an opt-in flag with at most five participants for 14 days;
   do not introduce multiple unproven Modes together.
7. Defer automatic mode routing until two Modes independently pass and explicit-selection evidence
   demonstrates that switching friction is a real problem.

Evidence may reorder or end a branch. A documented Do Not Build outcome is valid.

### 2026-08-29 — Release evidence and resolution

Every specialized Mode must pass its demand gate, deterministic contract tests, ticket 09 model
evaluation, moderated usability, and its own 14-day opt-in trial before it can ship.

- Deterministic tests enforce all Tool, data, transition, retention, and cross-Mode boundaries.
- All five moderated participants must identify the active Mode and its limits; at least four must
  enter, exit, hand off to Daily, and control Interaction Style without help.
- At least three trial participants must use the Mode on three separate days, report that it helped
  its defined user job, and choose to retain it.
- Coach additionally requires three participants engaged for at least seven days, compliant
  check-in timing and anti-nag behavior, and no reported increase in guilt, pressure, or dependency.
- Reflect additionally requires the wellbeing gate, at least ten completed reflections with 80%
  rated helpful, and no clinical claim or unintended durable storage.
- Recommender additionally requires correct freshness and attribution for every item, at least 80%
  relevant ratings, and no hidden purchase or affiliate relationship.
- Interaction Style changes remain confirmed, inspectable, and resettable; prohibited signals
  produce no proposal, and at least 80% of ten eligible proposals must be accepted or judged
  accurate before suggestions expand.

Stop immediately for an unauthorized Tool, cross-account or cross-Mode leakage, hidden adaptation,
clinical claims, anti-nag violations, unsafe or stale recommendations, or failed privacy controls.
Silent automatic adaptation and automatic mode routing remain unapproved future decisions.
