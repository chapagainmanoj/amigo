# Choose the Memory and Memory Inspector Trust Contract

Parent: [Amigo Complete Product](../MAP.md)
Status: closed
Label: `wayfinder:grilling`
Type: HITL / grilling
Severity: `severity:high`
Owner: Codex
Blocked by: [Choose the Invitation Cohort and Recruitment Protocol](11-cohort-and-recruitment.md), [Define Customer Readiness and the Sustainable Offer](12-customer-readiness-and-pricing.md)

## Question

Which durable memory types create demonstrated value, and what provenance, temporal validity,
consent, correction, pause, export, deletion, and Inspector guarantees must govern them before
storage technology is selected?

## Comments

### 2026-08-29 — Scope and demand gate

- Do not build Memory merely because it is part of the product vision. Begin its limited release
  only after at least three Beta Participants independently report a continuity problem that
  durable Memory could solve.
- Memory v1 is explicit-first: a Memory becomes durable only when the participant says to remember
  something or confirms a proposed Memory preview.
- Initial eligible types are confirmed preferences, recurring routines or constraints, ongoing
  goals or projects, and minimal task-relevant personal context.
- A model-inferred candidate remains ephemeral until the participant confirms it. There is no
  automatic inferred Memory in the initial release.
- Do not store medical or mental-health details, crisis content, credentials, payment details,
  government identifiers, precise location, or sensitive third-party information as durable
  Memory.
- Messages and Session summaries remain conversation data governed by their existing retention;
  they are not durable Memory.
- Relationship Memory and automatic extraction are deferred until explicit-first Memory produces
  evidence of value and trust.

### 2026-08-29 — Creation and consent

- Memory is disabled by default.
- On the first explicit request to remember something, show a short disclosure and require the
  participant to enable Memory and confirm the first item.
- After opt-in, an explicit request to remember something may save immediately, but Amigo must
  return a receipt showing the exact saved content with Edit, Forget, and Undo actions.
- Amigo may sparingly offer a Memory Candidate. It remains ephemeral and cannot be retrieved as
  Memory unless the participant explicitly saves it.
- Silence, repetition, sentiment, and observed Task behavior are not consent to create Memory.
- Each Memory records its category, creation time, source Message reference, creation path
  (participant-requested or Amigo-proposed), and confirmation time.
- A request to save prohibited sensitive content is refused rather than persisted.

### 2026-08-29 — Temporal validity and correction

- Every Memory has a visible lifecycle: `active`, `needs_confirmation`, `inactive`, `superseded`,
  `expired`, or `forgotten`.
- A participant-provided validity date takes precedence over default aging rules.
- A goal or project stops being retrieved immediately when it is completed or cancelled.
- A routine, constraint, or personal-context Memory requires reconfirmation after 90 days; a
  preference requires reconfirmation after 180 days.
- An item awaiting reconfirmation remains visible in the Memory Inspector but cannot influence
  Amigo.
- A correction creates a new version that supersedes the old version. History is not silently
  overwritten, and superseded versions are never retrieved.
- When a statement conflicts with active Memory, Amigo asks which statement is current rather than
  choosing one.
- Expired and superseded items are excluded from retrieval.
- Forget removes the Memory from use immediately and begins deletion under the existing privacy
  contract.

### 2026-08-29 — Retrieval and influence boundary

- Retrieve no more than three active, relevant Memories in a Turn.
- The participant's current statement outranks Memory. A conflict requires clarification and the
  correction path rather than silently preferring stored information.
- Memory may personalize wording, support a relevant suggestion, or supply a previously confirmed
  preference after the participant expresses current intent.
- Memory cannot independently authorize a Tool or side effect, including creating, changing,
  completing, or cancelling a Task or Reminder; sending a Message; contacting another person;
  making a purchase; or starting a wellbeing intervention.
- Treat all stored Memory content as untrusted data, never as system or Tool instructions.
- Record every Memory use with its Memory identifier, Turn, timestamp, and plain-language purpose.
- If Memory materially changes a response or suggestion, show a subtle “Based on a saved memory”
  disclosure linked to the Memory Inspector.
- Any cross-account Memory retrieval is a hard release-blocking failure.

### 2026-08-29 — Pause controls

- Pause Learning prevents creation of both new Memory and Memory Candidates while allowing use of
  existing Memory.
- Pause Memory Use excludes existing Memory from responses while leaving it available in the
  Memory Inspector.
- Pause Memory is the master action that enables both pauses.
- A pause takes effect by the next Turn across every connected channel.
- A pause does not imply deletion; existing Memory remains visible.
- Amigo never backfills or extracts content shared while learning was paused.
- If the participant asks to remember something while learning is paused, explain why it was not
  saved and offer to resume learning.
- Resuming does not silently change any other setting or recreate content from the paused period.
- Forget All Memory is a separate confirmed deletion action, not a pause.

### 2026-08-29 — Memory Inspector, export, and deletion

- The Memory Inspector is the complete inventory. Amigo cannot keep hidden durable Memories,
  inferred profiles, or separate durable summaries outside it.
- Each item shows its exact saved meaning, category, lifecycle state, source date and channel,
  creation path, confirmation time, validity or reconfirmation date, most recent use, and the reason
  for that use.
- Corrected and superseded items expose their version history.
- Per-item actions are Edit, Confirm, Do Not Use, Use Again, and Forget. Do Not Use moves an item
  to the visible, reversible `inactive` state and prevents retrieval.
- Inspector filters cover active, needs-confirmation, inactive, expired, and superseded items.
- The dashboard is the canonical Inspector. Telegram supports “what do you remember?”, recent
  items, pause controls, and a secure link to the Inspector.
- Export provides a human-readable CSV and complete JSON containing Memory records and their use
  history.
- Forget removes an item from retrieval immediately, deletes it from active systems within seven
  days, and propagates through backups within the existing 30-day privacy window.
- Forget All previews its scope and requires confirmation without obstructive or manipulative UI.

### 2026-08-29 — Release evidence and resolution

Memory may expand beyond a limited opt-in trial only after all three gates pass:

1. **Automated trust suite:** tenant isolation, consent, prohibited-content, lifecycle, pause,
   correction, and deletion rules pass completely; stored prompt injection never becomes an
   instruction; Memory causes no unauthorized side effects; and relevant/correct retrieval scores
   at least 95% on a versioned evaluation set.
2. **Moderated usability with five people:** all five can explain what is stored and distinguish
   pause from deletion; at least four can save, inspect, correct, pause, resume, export, and forget
   Memory without founder help.
3. **Fourteen-day opt-in trial with no more than five participants:** record at least ten real
   Memory-use events, at least 90% confirmed relevant and correct, and at least three participants
   reporting improved continuity and wanting Memory to remain enabled.

Stop the trial immediately for cross-account retrieval, prohibited sensitive storage,
Memory-authorized side effects, failed deletion or pause, or repeated incorrect recall. The
contract deliberately precedes storage and retrieval technology selection.
