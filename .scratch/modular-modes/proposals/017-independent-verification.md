# Migration 017 verification — 22 October 2026

Status: local verification passed; repository adoption only, no Supabase application or deploy.

## Artifacts verified

SHA-256 of the reviewed bytes:

| Artifact | SHA-256 |
|---|---|
| `migrations/017_mode_conversations.sql` | `1992fe4635fce27f09965b66732505e04fde4ec2a6a6f4b8d6371823748b8bcd` |
| `tests/sql/assert_017_mode_conversations.sql` | `ff4c692035d8e5fd26e369a75a40cdf592532bf16bda07f3cba94e06965ac8a6` |
| `scripts/check_mode_handoff_execution.py` | `80526cd9d9975f70306941e775cb8a9daf64f94246d277435962a108bfd3b713` |

Any subsequent byte changes require refreshing this evidence.

## Review provenance and corrections

The Store/migration author and the independent reviewer are separate agents. The independent
reviewer (`dev_runtime`) inspected 017 and reran its SQL assertions successfully with rollback.
The root agent supplied the full-chain/schema-gate/Activation-probe results below. The Store
agent separately ran the fresh-database backfill/concurrent-claim probe recorded here. That last
probe is additional execution evidence, not a second independent review of its author's code.

Review corrections incorporated:

- The local endpoint identity key now follows JSONB numeric identity, including nested arrays
  and objects: `1` and `1.0` name the same endpoint. For large integral floats, conversion uses
  `Decimal(str(value))`, matching serialized JSON rather than binary `int(float)` rounding
  (`1e23` equals integer `10**23`). Stored endpoint values retain their original representation.
- Append-only plan equality also follows JSONB: booleans remain distinct from numbers, so Python's
  `True == 1` cannot authorize a changed stored model step. Numeric `1 == 1.0` remains valid.
- The first execution claim requires an owned open target-Mode Session. Recovery retains the
  existing owned Session even after rollover closed it; it cannot rebind another Session. This
  preserves the Session and command receipt identity across a crash. The execution clock and
  persisted model-response plan also remain fixed across recovery.
- Claim tokens fence stale workers. Plan save and completion acquire the handoff row lock before
  checking the current lease clock. This avoids intentionally authorizing a write using a lease
  check made before a lock wait. Sequential expiry/fencing is exercised below; this record does
  not claim a forced lock-wait-expiry test unless separately reported.

Focused Store contracts after these corrections: **87 passed in 0.09s** (20 new cases plus 67
existing 016 cases). Owned-file Ruff and `git diff --check` passed. The adapter checks verify RPC
parameters and owner/Mode read filters; they are not a substitute for executing SQL.

## Fresh local PostgreSQL chain and prior probes

Cluster: PostgreSQL 15, temporary Unix socket `/private/tmp/amigo-mode017-f9p6t05_`, port `55491`,
local owner `mano`. Primary verification database: `amigo017`. No production credential or `.env`
was used. The root agent reported:

- The **37-file CI SQL chain**, using the `-f` sequence in `.github/workflows/ci.yml`, passed
  through 017 assertions and the application schema-version assertions.
- An independent reviewer reran `tests/sql/assert_017_mode_conversations.sql`: **passed**, rolled
  back fixture state.
- Schema-chain probe: all eight pre-014 gap cases and predecessor refusals for 015, 016 and 017
  passed; the complete chain reported **17**.
- Activation lock-order probe: forced interleave passed; **30 trials / 155 calls** passed. This
  remains evidence for the Activation interleave, not every possible handoff lock interaction.

Recorded root probe commands, with the local PostgreSQL executables on PATH:

```bash
PATH=/opt/homebrew/opt/postgresql@15/bin:$PATH \
PGHOST=/private/tmp/amigo-mode017-f9p6t05_ PGPORT=55491 \
PGDATABASE=amigo017 PGUSER=mano \
.venv/bin/python scripts/check_schema_chain.py

PATH=/opt/homebrew/opt/postgresql@15/bin:$PATH \
PGHOST=/private/tmp/amigo-mode017-f9p6t05_ PGPORT=55491 \
PGDATABASE=amigo017 PGUSER=mano PGOPTIONS='-c role=service_role' \
.venv/bin/python scripts/check_activation_lock_order.py
```

## Additional fresh-database backfill and execution probe

Actual command run by the Store agent:

```bash
PATH=/opt/homebrew/opt/postgresql@15/bin:$PATH \
PGHOST=/private/tmp/amigo-mode017-f9p6t05_ PGPORT=55491 PGUSER=mano \
.venv/bin/python scripts/check_mode_handoff_execution.py
```

The script accepts only a temporary local Unix socket. It creates a uniquely named database,
loads bootstrap plus migrations 001–016 there, seeds existing Sessions before 017, and applies
017 only to that new database. It never resets or writes fixtures into `amigo017`. New probe
DBs are retained for inspection within the temporary cluster. Initial successful run used
`amigo017_verify_a5a3bcdf5522`; the final exact script bytes ran in
`amigo017_verify_6589dad80770` with this output:

```text
database: amigo017_verify_6589dad80770
PASS: 016 existing coach/null-active Sessions backfill coach/daily; schema=17
PASS: 8 concurrent claim RPCs => 1 claimed, 7 busy; replay plan persisted
PASS: expired token fenced; closed bound Session/clock/plan retained; terminal replay refused
Scope: durable claim/replay state only; no model, Tool, Telegram, or Supabase calls
```

The eight clients synchronize their launch before calling the claim RPC. This verifies a single
lease winner under concurrent clients. It is not a forced-interleave deadlock proof. The probe
then persists a synthetic model-response plan, expires the first lease, closes the bound Session,
and verifies recovery preserves that Session, clock and plan while changing the claim token and
incrementing attempts. The expired token cannot save or complete; the current token can complete;
a subsequent claim reports `executed`.

`ruff check scripts/check_mode_handoff_execution.py`: **All checks passed**. Whitespace check clean.

## Limits

A durable lease and persisted replay plan do not themselves prove exactly one Task/Reminder side
effect. That requires application crash tests proving stored model-step replay and stable command
receipts across the relevant Tool-commit/completion boundary. This probe executes no model or Tool.
The full Phase 4 application suite, Telegram end-to-end flow, production configuration and external
migration application remain separate evidence and owner actions.
