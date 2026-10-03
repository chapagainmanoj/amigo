# Proposal: migration 016 — Session Modes, trial grants, confirmed handoffs

Status: adopted in the repository after owner approval and independent review; not deployed
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
- Independent concurrent probes executed with explicit live blocker transactions and observed
  `pg_stat_activity` lock waiters. Eight simultaneous grant requests produced five grants and
  three cap refusals; four simultaneous confirmations produced one confirmation and three
  replay refusals. Handoff expiry after a Session lock wait returned `expired`; grant expiry after
  that wait returned `unavailable`. Concurrent revoke prevented both entry and confirmation.
- An independently reproduced blocker in the earlier bytes: `grant_mode` could wait on the profile foreign
  key after its final clock refresh and return `granted` after the requested expiry. The persisted
  probe holds that profile row, observes the blocked request, crosses expiry, and asserts refusal;
  earlier SQL instead returned `granted`. The correction and successful independent retest below
  supersede that failure. All generated fixture rows and injected pairing gates were
  cleaned/restored in the probe's `finally` block.
- The same persisted probe reproduced one crossed-pairing deadlock with migration003's original
  function and zero with reconstructed015's ordered locks. The gate is injected after the first
  identity-row lock; both workers are observed blocked before releasing it.

Reproduction command (isolated actual reconstructed015→016 chain, not stand-in015):

```bash
.venv/bin/python .scratch/modular-modes/proposals/probe_015_016_concurrency.py \
  --host /tmp/amigo-mode016.pFi5g5 --port 55476 --database amigo_pairing
```

The earlier execution returned exit1 solely for the profile foreign-key expiry finding. The final
retest below passes that regression; migration approval does not imply production adoption.

## 2026-10-03 — Profile foreign-key expiry correction prepared

The reproduced `grant_mode` race is corrected in the parked proposal only. After taking the
per-Mode advisory lock, the function locks the owned `user_profiles` row `FOR KEY SHARE`, refuses
a missing owner, then refreshes `clock_timestamp()` and checks the requested expiry. The same
post-lock time is used for expiration cleanup, capacity decisions, and explicit `granted_at`.
The eventual grant INSERT's foreign-key check reuses this transaction's parent-key protection
rather than introducing a new parent-row wait after the final expiry validation.

Lock ordering is Mode advisory → owned profile key-share → grant rows. Revocation uses Mode →
grant; handoffs use ordered Mode locks → Session → handoff. This grant function does not acquire
Session locks or take another Mode lock after its profile lock. Profile key-share locks for
different Modes are mutually compatible; the scoped existing RPCs introduce no reverse ordering.
Independent reviewer agreed this ordering is coherent. This does not authorize arbitrary owner
transactions to violate the documented ordering.

Assertions now cover missing owners, past explicit expiry, and absence of grant/audit side effects
for both refusals. The existing reviewer-owned live-blocker probe already tests expiry crossed
during a profile lock wait; it was not duplicated or changed by this correction.

The independent fixture update/retest below certifies these corrected bytes. The earlier failure
is retained as regression evidence; no production adoption is performed by this review.

Current correction review bytes:

- 016 SQL SHA-256: `d08b4e28366982d06e2e1c5de1aa8088d90b09bf505e515accf3a0615d70c3df`
- Assertions SHA-256: `b1f81a37d440a81c22b14bcde246a57324cb7a6b89526bf8dbae0b1585c2a72e`
- Final concurrency probe SHA-256: `4cde64ec789b8f4cbd193228954d285b773d3c0da4958baac86795e1b4d01468`

## Final independent review — PASS

The independent reviewer installed only the exact corrected `grant_mode` proposal body in the
verified isolated actual reconstructed015→016 fixture and reran the current rollback assertions
and the complete persisted probe. Command returned exit0:

```bash
.venv/bin/python .scratch/modular-modes/proposals/probe_015_016_concurrency.py \
  --host /tmp/amigo-mode016.pFi5g5 --port 55476 --database amigo_pairing \
  --refresh-grant-proposal
```

Results: rollback SQL assertions passed; eight blocked concurrent grant calls yielded five
grants and three cap refusals; four blocked concurrent confirmations yielded exactly one
confirmation and three unavailable results. Handoff expiry after Session locking returned
`expired`; grant expiry after Session locking returned `unavailable`; grant expiry after profile
key locking returned `invalid`. Revocation serialized before both entry and confirmation returned
`unavailable`. Original003 crossed pairing yielded one forced deadlock; reconstructed015 yielded
zero and two conflict results. Every gate stayed live until actual lock waiters were observed;
expiry tests crossed real wall time while the request remained blocked. Pairing instrumentation
was restored and synthetic rows removed in `finally`.

Standards PASS; specification PASS for the parked schema proposal. No unresolved review finding
remains for the current SQL/assertion hashes above. Application Issue03 implementation and its
Store-sync/handler tests remain separate work; these SQL results do not claim those are complete.
The reviewer changed no protected migration/configuration file and performed no production action.
