# Migration020 independent verification

Reviewer dev_runtime, independent of migration/Store author usage_gate. 22 October2026. No SQL or author Store edits by reviewer; reviewer owns the separate Memory application/API layer.

Applied/reviewed migration SHA-256 `273f33cc8a383c1b7362798721cedf2d07a67d07b44b59fd77e9bd346922481b`.
Reviewed author assertion SHA-256 `bfdba78d3566695e33a9c19bcbae9f3dab92265ab90684a70f8842de0f79abd7`.

## Standards and spec review

All six tables have RLS enabled and no PUBLIC/anon/authenticated/service_role direct data privileges. Only service_role may execute the SECURITY DEFINER RPC; empty search_path and fully qualified owned table access preserve tenant scope. Default singleton admission ready=FALSE has no service-role setter. Owner identity comes from the authenticated application boundary, not Memory/model content. SQL validates exact digest, optimistic versions, source Message ownership/Mode, temporal validity, first-item atomic opt-in, at most five opted-in owners, maxthree scoped relevant records/Turn and fixed content-free use purposes. No plaintext candidates/receipt snapshots persist. Forget wipes saved text/provenance/scopes across versions and use rows; replay dereferences current row/tombstone rather than resurrecting deleted text. This is active-database proof; no backup/provider deletion promise is certified.

Reviewer findings corrected by author before adoption:

1. Missing/null expected_settings_version had bypassed SQL `<>`; now IS DISTINCT FROM matches local Store denial.
2. Nonforgotten table CHECK admitted SQL NULL text/source fields; explicit nonnull guards now enforce invariant.
3. Required-object/default-OFF guard now precedes ledger20 insertion.

Semantic sensitive-content classification is intentionally outside SQL and remains a reviewed application prerequisite. Default-deny injected eligibility in the application does not claim a keyword list or model self-report proves sensitivity detection. No actual participant admission approved here.

## Fresh independent PostgreSQL proof

`/tmp/amigo-review020.py` created `/private/tmp/amigo-review020-mc9skpfw`, PostgreSQL15 port55520, trust auth only on a temporary local Unix socket. Bootstrap + migrations001–020 applied from frozen per-file copies,21 files. Cluster stopped after proof. No Supabase or existing database reset.

Exact output:

```
020 source SHA256: 273f33cc8a383c1b7362798721cedf2d07a67d07b44b59fd77e9bd346922481b
PASS fresh bootstrap001–020: 21 files
PASS author020 owner/default-OFF/token/scope/version/forget/role assertions
PASS independent null-CHECK/version, foreign source rollback, settings-token freshness, correction, purge and stale-receipt probes
PASS Python/PostgreSQL exact Unicode ordered-array digest parity
PASS six independent first-opt-in SQL transactions: five admitted, one refused; atomic global cap
20|5|5
```

Author assertions and adversarial SQL run in rollback transactions. Last count20|5|5 is the explicit committed six-way fictional admission fixture: schema20, five enabled owners, five confirmed records; sixth owner remained unadmitted. Independent probes assert NULL field checks, missing optimistic version, foreign source partial-write rollback, pause/settings invalidating pending token, correct version supersession, retrieval of current version only, purge of all versions/use history, stale receipt replay returning no plaintext and preservation of source Messages. Python and PostgreSQL digest exactly match non-ASCII text `Fictional café ☕ preference`.

Exact driver/probes retained beside this record in `020-independent-probes/` with original /tmp filenames. SHA-256:

- `amigo-review020.py`: `5fd95b1166241eac7967e416920a5b135896d19fbf37e83a5b38b8adfceb0cc3`
- `amigo-review020-extra.sql`: `1efbe1e6ceb43a601bae3b000caf387a3a095927a2b76be1ae48c37aecaf470b`

## Store/application tests and limits

`pytest tests/test_memory_service.py tests/test_memory_store.py -q` →47passed1.19s. Service fixture exercises both local Stores; Store contract suite exercises InMemoryStore, FakeStore and production RPC DTO adapter. This adapter double validates method/DTO parity and is not claimed as SQL execution; the separate fresh proof covers PostgreSQL semantics. Default-deny eligibility, owner-bound process-local preview, kill/TTL/restart, correction/share/reconfirm, pauses, rights after admission kill, retrieval ledger/disclosure, compact channel confirmation/receipt Undo and activated owned API/export/error-redaction checks pass.

Verdict: no unresolved blocking finding in exact migration020 bytes. Semantic eligibility quality, demand/usability/trial, provider/backup deletion, deployment and automatic Mode retrieval remain outside this evidence. Memory stays default OFF; Daily instructions and Tool schema remain unchanged.
