# Coach preparation: migration 018 and Store contract proposal

Status: implementation design approved internally by the root agent under the build-plan gates.
Migration 018 and mirrored Store integration drafted; independent review required before adoption. Source: Issue 04, decision 14, current build-plan Phase 5.

## Scope and gates

Build one participant-chosen, participant-approved Coaching Program with versioned lifecycle and
self-reported entries. Default duration is 14 days. No Task/Reminder Tools, inferred progress,
Memory writes, clinical claim, automatic extension, or live registration in this preparation.
The standalone local state implementation is a testable design, not a live Store or privacy gate.

Privacy prereqs are missing: decision 04's published data inventory/consent does not explicitly
cover Coaching Program content, success measures and progress history. No export, deletion or
retention implementation was found under `src/` or `scripts/`; Issue 04's reference to “existing
export and deletion paths” therefore cannot be satisfied by adding columns alone. Owner must
approve inventory/purpose/retention/consent changes before participant data enters this feature.
Do not claim existing Message retention, seven-day exports/deletion or backup erasure is
implemented for coaching. Preserve those as obligations, not product assurances.

## Proposed migration 018_coaching_programs.sql

Follow 017 guard/schema-chain conventions, additive and service-RPC-only:

- `coaching_programs`: `program_id UUID PK`, `user_id` FK, goal, participant-written success
  measure, local check-in weekdays (ISO 1–7, unique nonempty), local time, IANA timezone, state
  (`draft|active|paused|completed|stopped`), `starts_at`, `ends_at`, `extended_count`, version,
  created/updated timestamps. Unique partial index on user_id where state is non-terminal,
  including drafts. No concurrent second draft while active or paused.
- `coaching_entries`: UUID PK, owned composite program/user FK, kind
  (`progress|weekly_choice|lifecycle|delivery`), participant text only for self-reported progress,
  explicit weekly choice, content-free delivery outcome, timestamps. Do not label scheduler
  observations as participant-reported progress. Allow no cross-Mode query.
- `coaching_approvals`: opaque one-use approval token hash, owned program/version/summary digest,
  expires_at, used_at. Issued by a trusted participant-facing summary-confirmation adapter.
  Activation RPC consumes only an authenticated participant confirmation matching the current
  version/digest. A model-supplied `approved=true` is never authorization.
- `coaching_command_receipts`: user/idempotency key, canonical payload hash, result, timestamps.
  Same key + same payload returns detached result; changed payload conflicts. Lifecycle update,
  entry append, token consumption and receipt commit atomically.
- RLS owned reads on program/entry tables, no direct mutations for authenticated/service roles;
  SECURITY DEFINER RPCs with empty search_path and explicit owner/version checks. Approval tokens
  and command receipts service-only; no raw token or content in telemetry.
- Add durable coaching delivery rows/outbox only after the shared budget decision below; do not
  pretend the existing scheduler_outbox (Reminder FK/payload contract) already accepts coaching.
  Schema bump, CI chain/assertions, predecessor guard and capability docs accompany adoption.

## Proposed Store API (mirror all three Stores)

All identities, idempotency metadata and approval receipts are injected by trusted adapters:

- `get_coaching_program(user_id, program_id=None) -> dict|None`: exact owned program, or current
  non-terminal program. `list_coaching_entries(user_id, program_id, limit=20) -> list[dict]`.
- `draft_coaching_program(user_id, idempotency_key, payload_hash, goal, success_measure,
  check_in_days, check_in_time, timezone) -> dict`: creates only draft, no scheduling.
- `change_coaching_program(user_id, program_id, expected_version, action, idempotency_key,
  payload_hash, approval_token=None, progress_text=None, weekly_choice=None,
  extension_days=None) -> dict`: atomic typed dispatch; no arbitrary updates dictionary.
- `revise_coaching_draft(...)`: explicit participant edits, version increment and fresh summary;
  an active program choosing Adjust pauses before revision. Existing start/end remain fixed unless
  separately extended; no silent fresh 14-day term.
- `issue_coaching_approval(user_id, program_id, expected_version) -> opaque UUID token` and
  `confirm_coaching_approval(user_id, token, idempotency_key, payload_hash) -> {program,entry}`: trusted adapter only; confirmation atomically activates the current approved draft and records the
  command receipt. Not model Tools.
- `complete_due_coaching_programs(now) -> metadata`: closes expired active/paused/draft-revision
  programs without content-bearing telemetry, cancels queued coaching deliveries transactionally.
- `export_coaching_data(user_id) -> {programs,entries}` and
  `delete_coaching_data(user_id, verified_request_id)`: integrate with approved whole-account
  export/deletion workflow; deletion first prevents future sends, then removes content, receipts,
  approval records, queued delivery payloads, cached Turn Context and existing export artifacts.
  Minimal content-free deletion proof belongs to the account deletion ledger, not these tables.

Lifecycle rules: draft → active only with matching participant approval; active → paused;
paused → active without changing approved config/term; any non-terminal → stopped; expiration
→ completed; completed/stopped cannot resume or extend. Extension is explicit, versioned,
1–14 additional days per request. Weekly Continue records intent without extension; Adjust pauses
for a fresh draft summary; Pause/Stop act immediately. Participant-reported progress never changes
state automatically. Mutations require expected version and append an owned event.

Approved implementation term is 14×24 hours from first activation (UTC instants); weekly day numbers
use the program timezone. If local-calendar-day duration across DST is desired, approve that
alternative before SQL adopts it. No duration promise is published by this preparation.

## Shared proactive budget and durable delivery: unresolved decision

Current Reminders do not enforce `daily_message_budget`; coaching cannot bolt on an independent
counter. Required design is one atomic per-user/local-day reservation ledger shared by ALL
proactive sends (Reminder, recovery summary, coaching check-in/follow-up/weekly review). Each
reservation has a stable delivery key and terminal/uncertain state; retries reuse it. At most one
coaching reservation per program/local day. Weekly review replaces a check-in. Quiet hours,
program/grant/consent state and owner endpoint are rechecked immediately before dispatch.
Paused/stopped/deleted/expired programs cancel queued work atomically. Delivery is through a durable
outbox with fenced claims and stable delivery keys; provider timeouts are uncertain, not a safe
license for duplicate sends.

Root integration owns the remaining policy for budget collision with an explicitly requested Reminder: suppressing it
would break an existing exact-time request; sending it over budget would break the new shared cap.
Owner must choose an explicit policy (e.g. reserve requested Reminder slots before accepting new
ones, with a clear refusal at scheduling time; Coach uses only remaining slots). Do not silently
skip, reschedule or exempt Reminders. This needs Reminder-command + dispatch changes and SQL
concurrency tests, not only a Coach scheduler job.

Missed check-in policy also needs a concrete scheduler rule: proposed next eligible selected day
may send one gentle follow-up (within the same one/day/shared budget), then suppress all further
coaching proactive work until an authenticated participant reply resets that gate. Whether weekly
reviews are suppressed during that silence must be approved; safest current interpretation is yes.

## Verification required before adoption

- Local/adapter/real SQL contracts: owner, one-open-program, stale versions, activation token
  replay/version mismatch, idempotency, explicit extension/stop, terminal behavior, export/delete.
- Fixed-Clock scheduler contracts: selected weekdays, timezone/DST, quiet-hour boundaries,
  weekly replacement, shared budget races with Reminders, follow-up then silence, pause/stop and
  restart. Crash injection across outbox claim/provider acceptance/completion.
- Export/delete seeded end-to-end verification under the approved consent/retention policy.
- Independent migration review + fresh full SQL chain. No Supabase application here.
- Coach eval/live-registration and external-trial release evidence remain separate gates.


## Implementation evidence (pre-integration)

- 018 SQL and assertions drafted; no Supabase application. Mirrored Stores delegate to a shared
  local lifecycle state and one production command RPC, plus service-only approval/rights RPCs.
- `src/memory/coaching.py`: default 14×24h UTC term, canonical UUID approval token, exact HH:MM
  schedule validation, owned/versioned lifecycle, immutable reply receipts, participant entries,
  scoped export and deletion of program/entry/approval/receipt content. No scheduler or model call.
- Focused local + three-Store adapter contracts: **29 passed in 0.05s**. Adapter tests do not execute
  PostgreSQL. Independent SQL review and fresh local application remain separate evidence.
- New reachable module `src/memory/coaching.py` must be in Gate A's invalidating fingerprint.
- Repository adoption authorized internally under the build plan; participant trial admission stays
  disabled pending privacy/consent/rights readiness, proactive delivery integration and final eval.
