# Review: Ordered Pairing Locks — Migration 015

Status: awaiting project-owner approval
Prepared: 2026-09-13

## Purpose

`public.complete_pairing`, created by migration 003 and untouched since, takes two
`user_profiles` row locks by two different keys — the Telegram chat id, then the Supabase auth
id — with no advisory lock and no fixed order. Two participants whose Telegram accounts are
crossed (row X = chat C1/auth B, row Y = chat C2/auth A) hitting their `/start` deep link at the
same time each lock the other's row first, and deadlock.

Both calls are destined to be refused with `conflict`, but the locks are taken **before** that
test runs, so one side receives a raw `deadlock detected` instead. `src/memory/store.py:907-913`
has no handler for it, so it reaches the Telegram pairing handler unhandled.

## Reproduction

An independent review reported 40/40 deadlocks. I could not reproduce it in 20 unforced trials
or in a first forced attempt, and said so rather than claiming their number. My construction was
wrong: holding one row makes both calls queue behind it in FIFO order, which is not a cycle.

The correct construction releases both calls from a common gate — a holder transaction locks
**both** candidate rows, both calls block on their *first* lock, and the commit grants both at
once so each then wants the row the other holds:

```
approved13 (migration 003 as shipped):   6/6 deadlocks
pair015    (migration 015 applied):      0/6 deadlocks, both calls return {"status": "conflict"}
```

That is the answer both calls were always destined for; the deadlock was the locks being taken
before the conflict test.

## The change

One function replaced. Every candidate row is locked first, one statement per row, ordered by
ascending `user_id`; the two reads that follow are unlocked because the rows are already held.
No branch of the function's behaviour changes — `paired`, `already_paired`, `conflict`,
`invalid_token`, and the adoption path are untouched.

## Honest limit of the measurement

Removing the `ORDER BY user_id` (mutant m1) did **not** reproduce the deadlock: with the loop
locking one row at a time, both calls happened to traverse the candidate set in the same
scan-determined order in every trial. So my evidence shows the per-row loop is what removes the
cycle, and the `ORDER BY` makes that order explicit rather than a query-plan detail that can
change silently. I am not claiming to have demonstrated the `ORDER BY` is load-bearing on its
own. The assertions require it to be present regardless, because an implicit order is exactly
the kind of thing that changes under a new plan.

## Verification

- The full CI chain plus 015 and its assertions applies clean to a fresh PostgreSQL 15 database.
- The deadlock probe: 6/6 before, 0/6 after.
- Assertions cover the happy path and the recorded identity, token consumption, idempotent
  re-pairing, the crossed-chat conflict, expired and unknown tokens, the required lock ordering,
  and that `anon` and `authenticated` still cannot execute the function.
- Mutation tested, all killed:
  - dropped `ORDER BY user_id` → `complete_pairing no longer orders its candidate row locks`
  - `GRANT EXECUTE ... TO authenticated` → `Authenticated role retained pairing access`
  - token not marked consumed → `Pairing did not consume its token`

## Hashes for approval

Superseded by the corrections below. Current bytes:

- `015_ordered_pairing_locks.sql`
  `c472a92019609a2eb2c84363f8799b8d95e8cb207e8a0f21308d8adb359192c6`
- `ordered_pairing_locks.sql` (assertions)
  `e9ccc369f252c29776491ab43979a2a8eddf42964e6cc05ef21125c320d911f4`

Both live in `/private/tmp/claude-501/-Users-mano-Workspace-amigo/fd470cab-1951-42d0-a839-05ddfd0b0e7f/scratchpad/migration-015/` and are **not** in `migrations/`.

## Adoption changes that must land in the same change

- `src/schema.py`: `EXPECTED_SCHEMA_VERSION` 14 → 15. The held chain test in
  `tests/test_schema_version.py` enforces this automatically and will fail until it is done.
- `.github/workflows/ci.yml`: append `-f migrations/015_ordered_pairing_locks.sql` then
  `-f tests/sql/ordered_pairing_locks.sql` to the psql chain.
- `scripts/check_schema_chain.py`: **already fixed, ahead of approval** — see the corrections
  below. Do **not** add `'14'` or `'015'` to `CONSTRUCTIBLE_SKIPS`; that advice was wrong.
- `README.md`: add step 17 and update the migration count.
- `.scratch/amigo-internal-preflight/issues/16-verify-single-owner-render-staging.md`: record the
  deadlock as fixed.

## Not yet reviewed independently

This record is written by the implementer. Per the standing rule for this work, an independent
agent must review these bytes before approval is acted on.

## Corrections after independent review

The review returned CHANGES REQUIRED with five blocking findings. Four are fixed; one is an
adoption-time change that cannot land before approval. My own account above was wrong in two
places and is corrected here rather than edited away.

**The re-reads lost their `FOR UPDATE`, and my "no behaviour changes" claim was false.** Migration
003 held a lock on exactly the rows it decided about. My loop locked the candidate set from one
snapshot and then re-read both rows *unlocked*, so a row that became the chat row after that
snapshot was conflict-tested and updated without ever being locked — and no unique index
backstops that update. The reviewer reproduced it: where 003 returns `conflict` and preserves the
earlier writer's identity, my version returned `paired` and silently destroyed it. Both re-reads
take `FOR UPDATE` again; re-locking a row the loop already holds costs nothing, and for anything
it does not hold it restores the EvalPlanQual re-check. Verified: the reproduction now returns
`conflict` and keeps the earlier identity, matching 003.

Not reachable through any shipped code path today — nothing clears `supabase_auth_id` — but 003's
safety was structural and mine had come to depend on that absence.

**The assertions were near-vacuous: 7 of 8 of the reviewer's mutants survived.** The worst was
003's exact deadlocking body with `ORDER BY user_id` left in a *comment*: `pg_get_functiondef`
returns comments, so the `LIKE` check passed while the function deadlocked 4/4. The converse was
also wrong — reformatting the `ORDER BY` across two lines failed CI despite byte-identical
behaviour.

The structural check now strips comments and collapses whitespace before matching, rejects
`ORDER BY user_id DESC`, and counts the row locks. New behavioural assertions cover the second
conflict arm, an invalidated token, a consumed token replay, `prosecdef` and the pinned empty
`search_path`, and PUBLIC privileges. Re-measured against mutants regenerated from the current
bytes:

```
m_noorder             killed   m_comment_only_order  killed   m_order_desc        killed
m_no_row_locks        killed   m_unlocked_rereads    killed   m_accept_invalidated killed
m_no_search_path      killed   m_drop_conflict_arm2  EQUIVALENT
m_no_revoke           EQUIVALENT                     s_reformat_order    survived (correct)
```

Eight of eight non-equivalent mutants killed, and the behaviour-identical reformat correctly
survives. The two equivalents are genuinely equivalent, not gaps:

- `m_no_revoke`: `CREATE OR REPLACE` preserves the existing ACL, so 003's REVOKE still stands —
  measured `PUBLIC execute=false`, `acl=postgres=X/postgres service_role=X/postgres`.
- `m_drop_conflict_arm2`: the unique index on `supabase_auth_id` plus 003's
  `EXCEPTION WHEN unique_violation THEN RETURN 'conflict'` produce the same observable answer for
  every input I could construct. The arm is defence in depth.

**`scripts/check_schema_chain.py` would have broken the moment 015 landed.** Its probe built each
incomplete chain from every migration except the skipped one and 014 — so 015 would have run
against a database with no `schema_migrations` table. Every probe would return "unbuildable" and
the CI step would go red in a way that reads like unrelated infrastructure trouble. Fixed ahead of
approval with a `GATE_MIGRATION` constant: only migrations *before* the gate take part. Verified
by dropping 015 into `migrations/` temporarily — all nine checks still pass — and removing it
again.

**`tests/sql/app_schema_version.sql` hardcodes 14 five times and probes forward with 15.** This is
the silent one: with 015 appended after that file, CI stays green while the file asserts a chain
revision the finished database does not have, and its `DELETE ... WHERE version = 15` would remove
015's genuine ledger row. It cannot be changed before 015 exists, so it is an adoption-time edit:
move 14 → 15 at lines 11, 12, 21, 22, 28, 84 and move the forward probe from 15 to 16.

**My `ORDER BY` framing was wrong in the other direction too.** I said the per-row loop is what
removes the cycle. The reviewer measured that the `ORDER BY` does change real acquisition order —
with rows laid out so physical order reverses `user_id` order, the ordered version locks by
`user_id` and the unordered one by page order. It is not decorative. It is also not strictly
necessary today, because every plan PostgreSQL 15 chooses for this predicate emits physical
order, which is itself a consistent global total order. The accurate claim: the per-row loop plus
*some* total order removes the cycle, and the `ORDER BY` pins which order rather than leaving it
to the planner.

### Adoption checklist, corrected

1. `src/schema.py` — `EXPECTED_SCHEMA_VERSION` 14 → 15. Enforced by `tests/test_schema_version.py`.
2. `.github/workflows/ci.yml` — append the migration and `-f tests/sql/ordered_pairing_locks.sql`.
3. `tests/sql/app_schema_version.sql` — 14 → 15 in five places, forward probe 15 → 16.
4. `scripts/check_schema_chain.py` — already done.
5. `scripts/check_activation_lock_order.py` — drop the "does not cover `complete_pairing`"
   disclaimer and add the common-gate trial, which is the behavioural deadlock proof. Held until
   adoption because it fails against the current chain, which is the correct answer today.
6. `README.md` step 17 and the 001–014 count, `docs/capability-matrix.md`,
   `docs/pre-launch-gap-analysis.md`, and issue 16.
7. Do **not** touch `CONSTRUCTIBLE_SKIPS`. No change needed in `src/memory/memory_store.py` or
   `tests/fakes.py` — both derive from the constant.
8. Adding 015 changes `all_invalidating_inputs_sha256`, invalidating any declared Gate A run.
   That is correct and is what `tests/test_gate_a_currency.py` exists to enforce; no declared run
   exists today.

### Disclosed and not fixed

015 blind-inserts its ledger row rather than earning it the way 014 does. It structurally cannot
be sentinel-verified by object existence, because `complete_pairing` already exists from 003 — a
consequence of a `CREATE OR REPLACE`-only migration. A future migration could add a marker object
a later gate can check. Re-running 015 also raises a primary-key violation on the ledger row, the
same as 014.

The reviewer's broader soak found migration 003 also deadlocking pairing against the Activation
functions — `get_activation_state`, `update_activation_profile`, and
`create_activation_test_command` were all deadlock losers in 10 of 8 rounds. 015 clears those too
(0 deadlocks in 20 rounds, 160 calls). Issue 16 had not recorded that wider blast radius.
