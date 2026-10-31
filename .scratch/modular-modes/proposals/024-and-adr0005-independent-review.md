# Independent review: e679a9b (ADR 0005 + ADRs 0006/0007), ef6b370 (SmokeChannel), 7deb2d6 (migration 024)

Reviewer: independent subagent, 31 Oct 2026. No push, deploy, Supabase, `.env`, Discord/Telegram or billed-model use.
Throwaway local PG15 DB `rev024_46899` created and dropped (`pg_database` count afterwards: 0).

## Verdict

- **Blockers: none.** Migration 024 is safe to approve as written.
- **Should-fix: 4** (S1 activation signal for legacy profiles, S2 ADR 0007 incomplete in ways that break its release steps,
  S3 review-queue entry missing for protected edits, S4 guard-ordering coverage gap).
- **Nits: 5.**

## Evidence run

| Check | Result |
|---|---|
| Full CI SQL chain (51 files, extracted from `.github/workflows/ci.yml` in order), `psql -v ON_ERROR_STOP=1` | exit 0, 0 `ERROR` lines |
| `PGDATABASE=<db> python scripts/check_schema_chain.py` | exit 0; last line `ok: migration 024 refused a missing ledger 23` |
| `PGDATABASE=<db> PGOPTIONS="-c role=service_role" python scripts/check_activation_lock_order.py` | exit 0; `the forced interleave held, and 30 trials (155 calls) found no deadlock` |
| `get_app_schema_version()` after chain | `24` |
| `complete_pairing_v2` catalog after 024 | `prosecdef=t`, `proconfig={search_path=""}`, `proacl={owner=X, service_role=X}` (no PUBLIC/anon/authenticated) |
| `python -m pytest tests/ -q -p no:cacheprovider -o faulthandler_timeout=30` | `1853 passed in 11.92s`, exit 0 |
| `ruff check src tests scripts` | `All checks passed!`, exit 0 |
| `python scripts/smoke_check.py --scheduler` (exit code read directly) | exit 0; `scheduler: in-memory APScheduler reminder fired through channel` |
| `python scripts/run_gate_a_eval.py --validate-only` (exit read directly) | exit 0; `validated amigo-gate-a-v1: 60 cases, 3 repetitions` |
| CLI dev fixture `_seed_dev_user(InMemoryStore())` | returns `primary_channel=cli`, `onboarding_complete=True`, identities `{'cli': '12345'}` |

## 1. Migration 024

**Body diff vs 022 (verified).** 022 is the only prior definition (`grep -ln complete_pairing_v2 migrations/*.sql` → 022, 024).
Extracting both bodies (022's `CREATE FUNCTION` normalised to `CREATE OR REPLACE FUNCTION`) and diffing:

```
41a42,46
>   -- ADR 0006: apps other than Telegram (and the local cli) only join an existing, activated
>   -- account; they never create one. The token stays unconsumed so the dashboard can explain.
>   IF p_channel <> 'cli' AND (NOT v_auth_exists OR v_auth_user.onboarding_complete IS NOT TRUE) THEN
>     RETURN jsonb_build_object('status', 'account_required');
>   END IF;
```

Byte-identical otherwise. Signature, `SECURITY DEFINER`, `SET search_path = ''` are restated; `CREATE OR REPLACE` keeps 022's
ACL (catalog above), and 024's own verification block re-asserts anon/authenticated denied and service_role granted.

**Guard placement** (`migrations/024_second_app_pairing_requires_account.sql:52-57`): after the token `FOR UPDATE`, the ordered
profile locks, the identity `FOR UPDATE` and `v_auth_exists`; before `already_paired`/`conflict`/insert. Early `RETURN` writes
nothing; row locks are held to end of the RPC transaction only (same as the existing `conflict` return). Token stays
unconsumed (asserted, and probed). Telegram returns earlier via `complete_pairing` (015), so it is untouched. Lock order
unchanged (lock-order script passes).

Ordering vs `already_paired`/`conflict`, probed on the chain DB:

```
unactivated, same identity already linked: {"status": "account_required"} consumed=f
unactivated, foreign identity:             {"status": "account_required"}
onboarding_complete NULL:                  {"status": "account_required"}
activated, already paired:                 {"status": "already_paired"}
activated, second fake2 id:                {"status": "conflict"}
activated, id owned by other account:      {"status": "conflict"} consumed=f
consumed token reuse:                      {"status": "invalid_token"}
```

Acceptable: `account_required` before `conflict` leaks nothing (the caller learns less), and an unactivated account holding a
non-Telegram identity can only come from pre-024 `complete_pairing_v2` (022/023 not yet applied in production per ADR 0004) or
the `cli` exemption.

**Ledger guard / verification / bump**: 024 refuses unless 1..23 all present and max=23 (`check_schema_chain.py` proves it:
`migration 024 refused a missing ledger 23`). Verification checks the body contains `account_required` and privileges.
`src/schema.py:3` = 24; `tests/sql/app_schema_version.sql` moved to 24 (and the forward probes to 25/26); CI order puts
024 + its assert before `app_schema_version.sql`; `scripts/check_schema_chain.py:43` adds 24; README step 26 and "001–024 /
schema-24" updated. Consistent.

**Mutation check of `tests/sql/assert_024_second_app_pairing_requires_account.sql`** (each mutant applied inside a
transaction, then the assert; `rc` read directly):

| Mutant | rc | Caught by |
|---|---|---|
| m1: no guard (022 body) | 3 | `024 created or consumed for an unknown account` |
| m2: guard consumes the token | 3 | same |
| m3: drop `onboarding_complete` test | 3 | `024 linked an unactivated account` |
| m4: drop `cli` exemption | 3 | `024 broke the cli first app` |
| m5: `IS NOT FALSE` (inverted) | 3 | `024 linked an unactivated account` |
| m7: exempt `fake2` too | 3 | `024 created or consumed for an unknown account` |
| **m6: guard moved after `already_paired`/`conflict`** | **0** | **survives** (see S4) |

### S1 (should-fix): `onboarding_complete` is not exactly "Activation complete" for legacy profiles

- In the 013 world the two are equivalent: `get_activation_state` (013:656-660) sets `onboarding_complete = TRUE` in the same
  call that computes `completed`, whenever `paired` (profile exists, 013:592). `update_activation_profile` resets it to FALSE
  (013:210) only before the test Task exists (013:190 `activation_profile_locked`). Migrations 014–023 never redefine
  `get_activation_state` or write the column (`grep -n onboarding_complete migrations/*.sql` → 001, 013, 024 only).
  The bot calls `get_activation_state` immediately before `complete_channel_pairing` (`src/bot/pairing.py:47`), so for the
  bot path `completed is True` implies the column is TRUE: **no new lock-out for activated full-access owners**.
- The divergence is the other way: pre-013 profiles onboarded through the legacy bot flow
  (`src/bot/onboarding.py:121-125` writes `onboarding_complete: True`; no longer wired in `src/`, only `tests/test_onboarding.py`)
  and later linked to a dashboard account via 015 adoption have `onboarding_complete = TRUE` with no completed journey. For
  them the DB guard says "activated" while `get_activation_state.completed` is false. The bot still refuses them, so nothing
  is reachable today, but ADR 0006's wording ("or its Activation is not complete") overstates what the DB enforces for any
  other caller.
- Fix (either): (a) guard on `EXISTS (SELECT 1 FROM public.activation_journeys WHERE auth_id = v_token.supabase_auth_id AND
  completed_at IS NOT NULL)` (plain read, no new lock; mirror in `identities.py` via the journey), or (b) state the legacy
  approximation in ADR 0006 and the 024 header. Before applying, the owner can quantify read-only on Supabase:
  `SELECT count(*) FROM user_profiles p WHERE p.supabase_auth_id IS NOT NULL AND p.onboarding_complete AND NOT EXISTS
  (SELECT 1 FROM activation_journeys j WHERE j.auth_id = p.supabase_auth_id AND j.completed_at IS NOT NULL);` and the
  reverse (`completed_at IS NOT NULL AND onboarding_complete IS NOT TRUE`, expected 0).

### Nit N1: the SQL `cli` exemption is unused in production

`cli` only runs on `InMemoryStore` (`src/cli.py:28,191`; `SmokeChannel` with `channel_id="cli"` only in `--scheduler`
with an in-memory store, `scripts/smoke_check.py:203`; `--channel` uses `TelegramChannel`). No production code passes
`'cli'` to `complete_pairing_v2`; only a service_role holder could, creating a Telegram-less `primary_channel='cli'`
profile. Low risk; the exemption exists for parity with the local mirror. Optional: drop it in SQL (the CLI never reaches
Supabase) and keep it only locally, or record the rationale as "parity only" in the 024 header.

### Nit N2: "The token stays unconsumed so the dashboard can explain" (024:53)

Nothing in `src/api/channels.py` or `web/src` reads `account_required` or the token state. The token simply expires. Reword.

## 2. Store parity (SQL vs InMemoryStore vs FakeStore)

Both local stores delegate to `LocalIdentityState.complete_pairing` (`src/memory/memory_store.py:1782`, `tests/fakes.py:1926`);
the guard is at `src/memory/identities.py:217-221` (same position: after token check and auth lookup, before owner/already_paired/
conflict). Probe `parity_probe.py` / `parity2.py` (scratchpad) on both stores:

```
('no profile', {'status': 'account_required'}, consumed=False, profile_created=False)
('unactivated same id', {'status': 'account_required'}, consumed=False)
('unactivated foreign id', {'status': 'account_required'})
('onboarding NULL', {'status': 'account_required'})
('activated already', {'status': 'already_paired'}, consumed=True)
('activated 2nd id', {'status': 'conflict'}, consumed=False)
('reuse', {'status': 'invalid_token'})
('activated, id owned by other', {'status': 'conflict'}, consumed=False)
```

Identical to the SQL probe for every status path, including token consumption. `is True` matches `IS NOT TRUE` for NULL.
`SupabaseStore.complete_channel_pairing` (`src/memory/store.py:1862`) is a pass-through, unchanged. Parity: OK.

## 3. Test fixture changes in 7deb2d6

`git diff 7deb2d6^ 7deb2d6 -- tests`:
- `test_channel_identity_store.py`: first-app test now asserts `account_required`, token unconsumed, no profile, then `cli`
  creates. Stronger. `test_second_app_links_…` adds the unactivated refusal before activation. Good.
- **S4-adjacent:** `test_telegram_as_second_app_…` and `test_pairing_conflicts_keep_the_token_and_identities` switched `fake2` →
  `cli`. The conflict/token-kept assertions now run only on the exempt channel; the conflict path for a real second app on an
  activated account is no longer covered in Python (the parity probe above shows it is correct). Not a hidden regression, but
  lost coverage.
- `test_mode_delivery.py:167-171` replaces pairing with `store._insert_user(...)` (private) to build a Telegram-less fake2
  profile. The delivery assertions are unchanged; acceptable, though that shape is now unreachable except via `cli`.
- `test_reminder_commands.py`: `fake2` → `cli` and source `"cli"`; assertion unchanged.
- `test_pairing.py:393-397`, `test_channel_neutral_handlers.py:40-42`, `test_discord_channel.py:186-188`: add an existing
  activated profile. Required by the new rule; no assertion weakened.
- New `test_database_guard_refusal_reaches_the_participant` covers `src/bot/pairing.py:82-86` by bypassing the bot check.
- CLI fixture still works (evidence table).

No meaningful assertion weakened.

### S4 (should-fix): guard ordering is untested

Mutant m6 (guard after `already_paired`/`conflict`) passes the SQL assert, and the Python tests don't cover an unactivated
account whose identity is already linked/foreign-owned. Add to `assert_024`: unactivated account + same identity already
linked → `account_required` and token unconsumed (with m6 this returns `already_paired` and consumes). Add the matching case
plus an activated `fake2` conflict case to `test_channel_identity_store.py`.

## 4. ADR 0005 implementation

- Protocol: `src/channels/base.py:104-118` declares `ready`, `connect_link` (properties), `start`, `close`.
- TelegramChannel (`src/channels/telegram.py:38-53`): class attrs `ready=True`, `connect_link=None`; `start()` calls
  `initialize(production=is_production(settings))` (`settings` imported at line 16); `close()` no-op. DiscordChannel:
  `ready` property (212), `start` (219), `close(*, drain_timeout=10.0)` (231, compatible), `connect_link` property (312).
  CLIChannel (`src/channels/cli.py:34-41`), FakeChannel (`tests/fakes.py:78-80,119-123`), SmokeChannel
  (`scripts/smoke_check.py:38-47`). Both `FailingChannel`s subclass `FakeChannel` (`tests/test_reminders.py:11`,
  `tests/test_scheduler.py:114`), so inherit everything.
- Fallbacks gone: `grep -rnE 'getattr\(...\"(ready|connect_link|start|close|initialize)\"|hasattr(...)' src scripts tests` → no hits.
  `ChannelRegistry.for_user` (`src/channels/registry.py:45`) and `api/channels.py:100` read attributes directly.
- `main.py` is unchanged by these commits: still `channel.initialize(...)` (line 143), `discord_channel.start()` under
  `wait_for` (150) and `discord_channel.close()` (188). `TelegramChannel.start()` has no caller; no runtime path can
  double-initialize. No `runtime_checkable`/`isinstance(…, MessageChannel)` anywhere, so nothing breaks at runtime.
- Nit N3: ADR 0005 "Consequences" lists five implementations and omits `SmokeChannel` (AGENTS.md now lists it).
- Nit N4: `tests/test_channels.py:120-137` lifecycle test doesn't include `SmokeChannel`, and never calls `TelegramChannel.start()`
  (a trivial monkeypatched `initialize` assertion would pin the ADR's "start runs initialize").

## 5. ADR 0007 accuracy

Grep of `src` (excluding egg-info) plus `pg_proc` on the chain DB (functions whose body mentions the legacy columns:
`_telegram_update_as_channel, claim_telegram_update, complete_pairing, create_activation_test_command,
finish_reminder_delivery, finish_reminder_delivery_v2, finish_telegram_update, get_activation_state,
mirror_telegram_identity, schedule_reminder_command`).

### S2 (should-fix): the list is incomplete, and two omissions break the release steps as ordered

Missing legacy reads/writes:
- `src/channels/telegram.py:236` `recipient_for` returns `user["telegram_chat_id"]` (the Telegram delivery address).
- `src/memory/store.py:141` `create_user` inserts `telegram_chat_id`; scripts `grant_mode.py:78` and `smoke_check.py:188`
  call `get_user_by_chat_id`.
- `src/scheduler/outbox.py:49` still reads `payload["telegram_chat_id"]` (hint; old outbox rows may carry it).
- `src/memory/store.py:1558` Later join (listed) — fine.
- `telegram_message_id` Python reads beyond the 013 predicate: `src/activation.py:138`, `src/memory/proactive.py:535`,
  `src/memory/activation.py:151`, write at `src/scheduler/reminders.py:461`.
- SQL: **`schedule_reminder_command` (023 version) still does `SELECT profile.telegram_chat_id INTO telegram_chat_id`**;
  `create_activation_test_command` reads `replaced_reminder.telegram_message_id`; `finish_reminder_delivery_v2` writes it.
  Step 3 (drop the columns in 026) breaks all three unless redefined; the ADR doesn't say so.
- Dead v1 Store wrappers (`store.py:247 claim_telegram_update`, `262 finish_telegram_update`, `1842 complete_pairing`) have
  no `src` callers outside `src/memory/`; worth naming for removal.

Step-order problems:
1. Step 1 says "no schema change" but includes "The Activation predicate … use[s] `channel_message_ref`". That predicate is
   SQL (`get_activation_state`, 013:609-610, and `create_activation_test_command`); changing it needs a migration. Move it to
   025 or make step 1 Python-only (local mirrors + PostgREST selects).
2. Step 2 revokes v1 functions from `service_role`, but CI's `scripts/check_activation_lock_order.py:124` calls
   `public.complete_pairing(...)` under `PGOPTIONS="-c role=service_role"` (ci.yml). 025 would fail CI unless the script moves
   to `complete_pairing_v2` in the same change.

Otherwise the order (code off reads → stop delegating → drop columns last) is sound and individually revertible.

## 6. Process

### S3 (should-fix): review queue has no entry for these three commits

AGENTS.md requires listing protected edits per phase. `.scratch/modular-modes/review-queue.md` ends at 15a4821's entry
(`git log -3 -- .scratch/modular-modes/review-queue.md` → 15a4821, c5d0654, 20dd82e). Missing: `scripts/smoke_check.py`
(ef6b370), `migrations/024_second_app_pairing_requires_account.sql` (7deb2d6), AGENTS.md edit (ef6b370), and the evidence
above. Also note this review covers the AGENTS.md-mandated independent migration review for 024.

### Nit N5

ADR 0004 still says "Status: Proposed" while 0005–0007 build on it as accepted; and ADR 0006 says the Telegram-only
check-then-act "is safe" because the token owner cannot change — true (tokens are immutable rows), but a second token could be
issued between calls; harmless since both calls use the same token.
