# Migration 023 independent review (commit 599f379)

Reviewer: independent subagent, 31 Oct 2026. Context commits ac1416f, 852e214, 4409044 read.
I did no push, deploy, Supabase apply, `.env` edit or billed model run. I edited no tracked files.

## Verdict

**No blockers. No should-fix items.** There are 5 nits, all optional.

## Verified claims

### 1. The producers are the latest definitions, and the only change is the removed line
- The only definitions of each producer in 001-022 are:
  - `schedule_reminder_command` in 006:116
  - `apply_later_command` in 008:3
  - `create_activation_test_command` in 013:235
- No later CREATE or REPLACE and no ALTER FUNCTION exists, including in 022:
  `grep -nE "FUNCTION[^(]*(schedule_reminder_command|...)" migrations/*.sql` and `grep ALTER FUNCTION`.
- I extracted the text from the CREATE line through `$$;` and diffed it against 023 (lines 13, 250 and 511):
  ```
  == 1  199d198 <       'telegram_chat_id', telegram_chat_id,
  == 2  219d218 <       'telegram_chat_id', user_row.telegram_chat_id,
  == 3  242d241 <       'telegram_chat_id', profile_row.telegram_chat_id,
  ```
- I also compared the catalog of a DB built to 022 with one built to 023. `prosrc` differs only by that line for all 3 functions.
- Signature, `prosecdef`, `proconfig` and `proacl` are identical before and after 023:
  ```
  schedule_reminder_command(...)      |t|{"search_path=pg_catalog, public"}|{mano=X/mano,service_role=X/mano}
  apply_later_command(...)            |t|{"search_path=pg_catalog, public"}|{mano=X/mano,service_role=X/mano}
  create_activation_test_command(...) |t|{"search_path=pg_catalog, public",TimeZone=UTC}|{mano=X/mano,service_role=X/mano}
  ```
  CREATE OR REPLACE kept the grants.

### 2. Rebuilding `list_pending_handoff_executions`
- No dependents:
  - `pg_depend` has 0 normal dependents.
  - No migration from 018 to 022 references the function.
  - SQL callers appear only in tests (assert_017, assert_023).
- Privileges and settings before and after 023:
  ```
  pre : |t|{"search_path=\"\""}|{mano=X/mano,service_role=X/mano}|v|TABLE(..., target_mode_id text, telegram_chat_id bigint)
  post: |t|{"search_path=\"\""}|{mano=X/mano,service_role=X/mano}|v|TABLE(..., target_mode_id text)
  ```
  The REVOKE covers PUBLIC, anon and authenticated, and the GRANT goes to service_role. This matches the 017 grants.
- 023 drops the 017 `JOIN user_profiles`. This does not change the semantics:
  `mode_handoffs.user_id` is `NOT NULL REFERENCES user_profiles(user_id)` (016:53), so the inner join never filtered rows.
  If a row ever has no owner, `HandoffController._recover_execution` already retires it as `owner_unavailable`.
- Rollout:
  - **Schema-22 code with a 023 DB is safe.** Code at 022 and later never reads the listing's `telegram_chat_id`.
    `git grep telegram_chat_id 599f379^ -- src/handoffs.py src/scheduler/outbox.py` shows only `payload.get(...)`.
  - The schema gate runs only at startup (`src/startup.py:9`). A running schema-22 process therefore keeps working
    until it is redeployed. A restart in that window fails closed, which is the intended behaviour.
  - **Schema-21 code with a 023 DB would break** (nit N1). Before 722fa73, `outbox.py:48` read `payload["telegram_chat_id"]`.
  - The new code cannot run against a 022 DB because the exact-match gate refuses it.

### 3. Store parity
- The InMemoryStore and FakeStore payloads are identical, `{scheduled_time, task_title}`. Both use:
  - `src/memory/later.py`
  - `src/memory/activation.py`
  - the same schedule dict at memory_store.py:1130 and fakes.py:1208

  These keys match the SQL `jsonb_build_object('scheduled_time', ..., 'task_title', ...)` at 023:210, 467 and 751.
- The listing shape is `{user_id, handoff_id, execution_session_id, target_mode_id}` in:
  - `LocalModeState.pending_executions` (modes.py), shared by InMemoryStore and FakeStore
  - the SQL RETURNS TABLE
  - Supabase, which passes the RPC data through (store.py:1060)
- No consumer of the removed fields remains:
  - The only remaining reader of payload `telegram_chat_id` is `src/scheduler/outbox.py:49`, which uses `payload.get(...)`.
  - That hint is overwritten at fire time by `_daily_delivery` (reminders.py:276 and 390).
  - No listing consumer reads the column. `web/src` has no hits.
  - Test stubs do not include the key (test_mode_maintenance.py:120).
- Outbox rows already in the DB that still carry the key drain fine, because `.get` ignores it.
  APScheduler `chat_id` kwargs are also replaced at fire time.

### 4. Tests, CI and the chain gate
- In ci.yml, `023` and `assert_023` come right after `assert_022` and before `app_schema_version.sql`.
- `PREDECESSOR_GATES` gains 22 and 23. 22 was missing before this commit; 023 fixes that omission.
- `app_schema_version.sql` now expects 23 and probes 24 and 25.
- `EXPECTED_SCHEMA_VERSION=23`.
- The 023 ledger guard checks two things:
  - versions 1-22 are all present
  - max = 22

  The ledger INSERT is inside the guarded DO block.

### 5. Local run (PG15, throwaway DBs, both dropped)
```
createdb amigo_review_023
psql -X -q -v ON_ERROR_STOP=1 -d amigo_review_023 <49 -f files from ci.yml, in order>   -> exit=0
psql -c "select get_app_schema_version(), ledger"  -> 23|1,2,...,22,23
PGDATABASE=amigo_review_023 python scripts/check_schema_chain.py                       -> exit=0
   ... ok: migration 022 refused a missing ledger 21
   ... ok: migration 023 refused a missing ledger 22
PGDATABASE=amigo_review_023 PGOPTIONS="-c role=service_role" python scripts/check_activation_lock_order.py -> exit=0
   ok: the forced interleave held, and 30 trials (155 calls) found no deadlock.
createdb amigo_review_022 + first 47 files (through assert_022) -> exit=0   (used for the pre/post catalog diff)
python -m pytest tests/ -q   -> 1802 passed in 21.71s
ruff check src tests scripts -> All checks passed!
dropdb amigo_review_023; dropdb amigo_review_022
```

## Nits

- **N1. Rollout note.** In schema-21 code, `src/scheduler/outbox.py:48` read `payload["telegram_chat_id"]`.
  - If 022 and 023 were applied together while schema-21 code is still running, every new schedule effect would raise KeyError.
  - Under 006:552-559, each effect would retry 5 times with backoff, about 31 s in total, and then become `failed`.
  - Startup `reconcile()` from the reminders table would recover these Reminders after the deploy.
  - README step 25 already says to apply 023 "in a later release, after 022 is live". Consider adding:
    "never apply 022 and 023 together while schema-21 code is running".
- **N2. Activation payload not covered after 023.** `tests/sql/assert_023_channel_neutral_producers.sql` runs Schedule and Later only.
  - `create_activation_test_command`'s payload after 023 is not asserted. activation_journey.sql runs at 013,
    and check_activation_lock_order only checks lock order.
  - The prosrc diff above shows the change is correct. A three-line assert would lock it in.
  - The Later check (line 34) also verifies only that the key is absent. It does not check that `task_title` and `scheduled_time` are present.
- **N3. No live listing row after 023.** assert_023 runs `PERFORM * FROM list_pending_handoff_executions(5)`, which probably returns zero rows.
  - No SQL test reads a real row through the new 4-column listing.
  - Python coverage exists for the local Stores only.
- **N4. Guard message (023:822-823).** One exception text, "023 producers still carry telegram_chat_id", also fires
  for missing functions or for `authenticated` holding EXECUTE. The message misleads when privileges are the cause.
  - The guard does not check that `anon` and `PUBLIC` lack EXECUTE; assert_023 checks only anon.
- **N5. Dead code and stale evidence.**
  - `schedule_reminder_command` still declares `telegram_chat_id BIGINT` and SELECTs into it (023:35 and 123).
    It is now used only as the `user_not_found` existence check. This is acceptable because it keeps the body byte-identical.
  - Gate A evidence is stale again, because `gate_a.py:184` hashes `migrations/*.sql` and the touched later.py, activation.py, modes.py and schema.py.
    This is expected, and re-running it needs owner approval.
  - PostgREST must reload its schema cache after the DROP/CREATE that changes the return type. Supabase's default DDL watch handles this.
    No migration has ever sent `NOTIFY pgrst`, so this is consistent with the repo.
