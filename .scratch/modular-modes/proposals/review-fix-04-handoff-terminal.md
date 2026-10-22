# Review item4 — terminal handoff recovery outcomes

Scope: isolated handoff-review-fixes worktree, based on b2c824f. This is item4 only; application
retry limits/notices/history/buttons (item3), backfill/lock changes (item11), and main maintenance
are separate slices. No production apply, model request or .env edit.

017 adds nullable execution_failed_at and content-free execution_failure_reason. Confirmed owned
claims with unusable target Session or withdrawn/expired target grant become terminal, returning
unavailable + terminal:true once. Later claims return failed; foreign/unconfirmed claims do not
mutate the row. Failed rows leave the partial pending index and LIMIT25 recovery queue. Successful
completion still uses executed_at. Saving plans and completing after failure are refused.

New fail_handoff_execution(user_id,handoff_id,claim_token,reason)->bool is mirrored in MemoryStore,
InMemoryStore and FakeStore. It admits only bounded reason codes and current owned lease tokens;
stale/foreign/expired/repeated failures fail closed. Its true result is available for the later
application slice's single notification attempt. No claim of exactly-once Message delivery.

Before fix:5 failed,2 passed in the new regression module;25 unavailable rows returned forever,
blocking the26th. After fix:30 focused contracts passed; full tests1332 passed in21.07s. Offline
scheduler smoke passed. Targeted Ruff clean and git diff --check clean. Full Ruff reports an
unrelated preexisting b2 I001 in scripts/grant_mode.py:32; this slice did not edit that script.

Author fresh PostgreSQL driver /tmp/amigo-handoff-item4-verify.py applied all45 CI SQL files,
including terminal/fencing/queue assertions; PASS. Unix-socket cluster
/private/tmp/amigo-handoff-item4-juaf1ycn, port55535, stopped. SQL017 SHA256:
745aab3dbc89412719bf6628f348a492f586f35fd73518743dc405f075c9aa8d.
Independent migration review assigned to usage_gate; commit waits for its result.

Independent usage_gate review PASS on exact hash above: own fresh45SQL chain; extra foreign claim
nonterminal, live-lease busy, expired/stale plan/fail/complete rejection, replacement token,
terminal single-use and25 unavailable→26th claimable probes passed. Own30 Store tests passed0.10s.
Driver /tmp/amigo-independent-handoff-item4.py; extra /tmp/amigo-independent-handoff-item4-extra.sql;
cluster /private/tmp/amigo-independent-item4-ipy58dbu stopped. No findings or source edits.
