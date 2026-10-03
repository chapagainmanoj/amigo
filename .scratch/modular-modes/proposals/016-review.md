# Proposal: migration 016 — Session Modes, trial grants, confirmed handoffs

Status: draft awaiting independent review and explicit project-owner approval
Prepared: 2026-10-03

These files are proposals only. Nothing has been added to `migrations/`, no Store or runtime
path depends on them, and the production schema/defaults remain unchanged.

## Chain prerequisite

The approved repository ends at 014. Migration 015's ordered pairing fix remains parked with
separate approval requirements in `.scratch/amigo-internal-preflight/reviews/015-ordered-pairing-locks.md`.
The old absolute paths to 015's SQL/assertion bytes no longer exist; this repository retains its
review record only. The missing proposal bytes must be reconstructed and independently reviewed
before 015 can be approved/adopted. This is a separate prerequisite, not silently resolved by 016.

016 refuses installation unless the ledger contains the complete 001–015 chain and its current
revision is exactly 15. Number 015 is reserved; this proposal does not adopt or approve it.

For isolated SQL verification against today's 001–014 chain, a fixture may insert a stand-in
015 ledger row after first proving 016 refuses the incomplete chain. That validates the Mode SQL
only, and must never be described as adoption/testing of the real 015 pairing fix. Final adoption
requires the independently approved real 015 bytes and its assertions followed by 016.

## Reviewable changes

- Nullable `sessions.active_mode_id`, with unchanged null/Daily behavior for existing Sessions.
- Owned-session composite identity prevents handoffs belonging to one participant referring to
  another participant's Session.
- Durable grants, one open grant per participant/Mode, at most five active participants per Mode,
  expiry at most 14 days, and immutable grant/revoke/observed-expiration audit records with actor
  and reason. Expired grants are closed and audited before renewal; duplicate grants are idempotent.
- Per-Mode advisory locks serialize capacity decisions, revocation, and handoff authorization.
  Handoffs acquire both involved Mode locks in lexical order, then Session, then handoff locks.
  Wall-clock expiry is rechecked after lock waits, with explicit grant/create/resolve timestamps.
- Confirm resolves exactly once and switches the owned Session in the same transaction. Decline,
  expiry, revoked grants, changed source Mode, closed Session, replay, and another participant's
  tap cannot enter the target or return a carried request for execution.
- RLS permits authenticated participants to read only their own records. Authority mutations are
  RPC-only, service-role-only; direct grant/handoff/audit DML is revoked even from `service_role`.
- 016 earns its ledger row from its newly created objects; adoption changes the application
  expected schema revision to 16 only after both 015 and 016 are approved.

The application must still enforce registered live Modes, declared handoff targets, and explicit
participant button confirmation. SQL owns tenant binding, atomicity, expiry, grants, and single use.
The service derives grant-required flags from authorized registry definitions; model Tool arguments
cannot supply these flags. Defaults require a grant for non-Daily Modes, while trusted false flags
preserve activated-participant Modes. Confirmation uses flags stored at proposal creation.
Carried request text is untrusted input to a new target-Mode Turn; it never becomes instructions or
Tool authorization. No model Tool is granted authority to confirm a handoff or grant trial access.

## Human choices proposed

Handoff expiry: **10 minutes**, fixed in the creation RPC and bounded by a table constraint.
Trial grant expiry: **14 days by default**, shorter periods allowed; a sixth concurrent active
participant is refused. Grants require an operator identity and a nonempty reason.

Participant wording proposed:

- `/mode`: "You're in {name}. Choose a mode for this session. You can return to Daily anytime with /daily."
- Entry: "You're now in {name}. {purpose}\n\nLimits: {limits}\n\nReturn to Daily anytime with /daily."
- Exit: "You're back in Daily for this session."
- Handoff: "Pass this request to {target_name}?\n\n{carried_request}\n\nNothing changes until you confirm. This request expires in 10 minutes."
- Buttons: "Confirm" and "Decline".
- Withdrawal: "{name} is no longer available for this session. You're back in Daily. I haven't processed your last message; send it again if you'd like Daily to help."

## Verification and rollback

`assert_016_session_modes_grants_handoffs.sql` covers additive defaults, cap, duplicate grants,
expiry/revoke/audit, owner binding, confirm/decline/expiry/replay, revoked-grant confirmation,
authenticated read isolation, and mutator privileges. Independent review must also prove concurrent
sixth-grant refusal and simultaneous confirmation using separate database connections.

Rollback is possible before application adoption by removing the new RPCs/tables/Session column
and ledger 016 row in one reviewed transaction. Once grants/handoffs exist, preserve/export those
records first; dropping them is data-destructive and requires explicit approval. Do not rewrite
015 or the existing ledger. No rollback command is executed by this proposal.

SQL execution verified on isolated PostgreSQL15, 2026-10-03:

- The approved001–014 chain applied cleanly; 016 refused the missing015 chain.
- A separate fixture applied001–014, the newly reconstructed015 proposal and its assertions,
  then current016 and its rollback assertions. All passed; this fixture uses actual reconstructed
  pairing SQL, not a stand-in ledger entry. These are unapproved proposals, not production adoption.
- Independent review's initial fixes were implemented: wall-clock checks after lock waits,
  atomic grant recheck on entry, registry-derived grant-required flags for activated Modes, and
  returned confirmation state matching committed resolution fields.
- Independent concurrent cap/confirmation/expiry/revoke probes: pending.

Current review bytes:

- 016 SQL SHA-256: `abf32d3a4923b51d826bcc032c071fad6f889ef2771c9aec4611648812e3eb52`
- Assertions SHA-256: `761ba50d8de1484bb86fc8a0a525fd7abca536ad7a6fbed471435b7b223a4777`
