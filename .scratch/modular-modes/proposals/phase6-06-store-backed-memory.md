# Issue 06 — explicit-first Store-backed Memory

Status: provisional — owner review
Date: 22 October 2026
Implementation: preparation only; disabled by default, no Memory data collected.
Sources: Issue 06; decisions 13, 26 and 30; build-plan Phase 6.

## Decision and limits

Prepare one owned Memory Service over the existing Store boundary. Use ordinary PostgreSQL rows,
explicit categories and bounded deterministic filtering first; no embeddings, vector database,
background extraction, separate processor or external Memory service. This is a provisional
implementation shape, not closure of decision 30: decision 26 has no recorded demand evidence
here, and its completion would authorize a demand conclusion rather than waive the trust contract.
Do not enable participant Memory or alter published privacy/retention promises during preparation.

Only a declared `memories` Turn Context provider may read the service. Daily is the first proposed
consumer; Coach requires a separately reviewed data contract, and Reflect gets no automatic Memory.
Default each item to the originating Mode's scope. Additional Mode scopes require an explicit,
inspectable participant sharing choice; a model cannot broaden them.

## Records and authority

Proposed owned Store records:

- `memory_settings`: enabled=false, learning_paused, use_paused, policy version and acknowledgment.
  Master Pause sets both flags; Resume changes only the specifically requested flag.
- Versioned `memories`: stable item/version identity, category, exact confirmed text, lifecycle,
  source Message reference/date/channel, creation path, confirmation time, allowed Mode scopes,
  participant validity date, reconfirmation date, supersedes link, optimistic version.
- Content-free `memory_uses`: owner, exact item version, Turn ID, time, allowlisted purpose code
  rendered as plain language. No copied Memory text in this ledger or telemetry.
- Owned idempotency/confirmation metadata sufficient to bind a preview to exact text/version;
  no model-supplied Boolean authorizes storage, sharing, correction or Forget All.

A proposed candidate remains ephemeral, bounded and non-retrievable, with a short process-local
TTL. Restart discards it rather than durably storing unconfirmed text. First use requires both
Memory opt-in and confirmation of the exact first eligible item. Explicit saves after opt-in still
return the exact saved content with Edit, Forget and Undo controls. Never backfill paused content.

Only confirmed preferences, routines/constraints, ongoing goals/projects and minimal task-relevant
context are eligible. Medical/mental-health/crisis content, credentials, payment/identity details,
precise location and sensitive third-party information must be refused before durable storage.
The eligibility/sensitive-content admission mechanism needs its own adversarial evaluation;
keyword checks or a model saying “safe” are not evidence of complete detection. Keep admission off
until that design and its failure behavior are reviewed.

## Service contract

All actor identities come from trusted authentication. Proposed methods are `propose`,
`enable_and_confirm`, `remember_explicit`, `correct`, `set_inactive`, `use_again`, `reconfirm`,
`forget`, `forget_all`, `set_pauses`, `inspect`, `export` and `read_relevant`. Every mutation is
owned, versioned and idempotent. Corrections create a new version and supersede the old one;
conflicting current statements require clarification, not silent replacement.

`read_relevant(actor, mode, turn, explicit_intent, relevance_filter)` returns at most three active,
confirmed, scoped, unexpired items. SQL filters ownership/lifecycle/scope before any relevance
ranking; the current statement outranks saved content. Participant validity wins; otherwise require
reconfirmation after 90 days for routine/constraint/context, 180 for preference. Goals/projects
stop retrieval when completed/cancelled. No silent global search fallback or model-selected owner.

Record each actual use and disclose material influence with “Based on a saved memory” linked to
the canonical Inspector. Use purpose codes with fixed explanatory text rather than logging free
model rationales. Memory is untrusted data and supplies no Tool authority: current authenticated
participant intent or a separately confirmed action remains necessary. A stored instruction must
not create a Task, Reminder, Message or other side effect.

## Inspector, rights and admission

The dashboard Inspector must enumerate all versions/states and use history, including inactive,
needs-confirmation, expired and superseded items. Telegram can list recent items and controls, with
an authenticated Inspector link. No hidden parallel summary store. Forget excludes retrieval
transactionally, then deletes content/derived indexes/caches under the approved deletion workflow;
Forget All previews scope and confirms. Export includes human-readable CSV and complete JSON with
use history. Pauses affect the next Turn across channels and do not imply deletion.

Existing decision 04 excludes durable Memory from current participation and specifies service
obligations that are not established merely by these proposed tables. Owner approval of updated
notice/opt-in, a functioning Inspector and seeded export/deletion/restore tests must precede any
participant activation. Do not claim seven-day active deletion or 30-day backup erasure without
verification. Database migrations and Store parity, trust-suite tests, fictional retrieval evidence,
moderated usability and the limited opt-in trial remain required; no demand/usability evidence is
invented by this record.

## Implemented Phase 6 candidate

Migration020 implements owned settings, versioned records, content-free uses, digest-only
confirmation claims and idempotency metadata. All three Stores expose the same contract. One
serialized admission cap admits at most five enabled owners (paused owners still count). Database
admission defaults false and cannot be changed by the ordinary service credential. Application
readiness and semantic eligibility independently default to denial; no keyword list is represented
as a sensitive-content detector. This build does not close demand, usability or privacy review.

The MemoryService owns bounded ephemeral exact previews and rechecks readiness after awaited
eligibility. Confirmation binds owner, operation, exact ordered payload digest, settings version,
item version and expiry. First save atomically combines opt-in and the exact item. Correction,
reconfirmation and sharing create versioned changes; broadening scopes needs a new visible preview.
Pause invalidates pending claims; resuming does not replay paused input. Provenance references are
owned, and explicit dashboard saves identify their real channel/path rather than fabricate a
conversation Message. Forget purges every version's plaintext/provenance and uses; replay cannot
return the deleted content. Forget All confirms the exact current inventory and rejects changes.

An optional candidate Toolset can only propose a preview; it has no confirmation Tool. No Mode
registers that Toolset or the optional `memories` context provider. Daily instructions/Tool schema
remain unchanged. Future context use is explicit-intent Daily-only, at most three across a Turn,
owned/scoped/current before ranking, with a content-free use ledger and influence disclosure.
Reflect never receives automatic Memory. The provider's output is untrusted data, not authority.
Actual material-influence rendering needs a separately reviewed Mode integration before enablement.

Authenticated Inspector API supports complete owned inventory/version/use history, separate
learning/use pauses, exact save/correct/reconfirm/share previews, item lifecycle, JSON/CSV and
scoped Forget. Channel controls inspect recent items and pause states, link to the canonical
Inspector, and bind confirmation/receipt controls to the authenticated participant. Review records
cover TTL/restart/kill, foreign callbacks/source Messages, scoped content purge, stale receipt replay
and preserved conversation data. No provider-copy or backup-erasure claim follows from these tests.

Independent SQL review found and fixed nullable CHECK validation, missing optimistic-settings
version validation and the incomplete pre-ledger object guard. Fresh PostgreSQL review verifies
Unicode Python/SQL digest parity, foreign-source rollback, settings freshness, correction/purge
and six concurrent first opt-ins admitting five. See `020-independent-verification.md`.
Seventeen versioned fictional retrieval fixtures pass exact expected-ID sets; this narrow authored
lexical corpus is not evidence of general 95% recall or complete prohibited-content classification.
Default-deny admission remains required pending actual reviewed eligibility, rights/retention,
demand, five-person usability and limited opt-in trial evidence.
