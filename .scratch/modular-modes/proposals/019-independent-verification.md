# Migration 019 independent verification

Reviewer: dev_runtime, independent of authors usage_gate (proactive) and root (Reminder triggers), 22 October 2026. No migration edits by reviewer.

Reviewed source SHA-256: `06e51e050c60a8247d21498ee6ce582cee09f1d38b77d781d360756f91d2e760`.
Reviewed assertions SHA-256: `f5acd7678bf61ef80ab518fa5a3f9e6b6779b50ed46852a3d51a1fd19e9e92cc`.

Spec/standards: approved Modes plan, Issue 04, AGENTS Store/side-effect/privacy boundaries; current uncommitted 019 authoritative bytes. RLS on all tables; anonymous/authenticated data access and mutating service-role table writes revoked; trusted RPCs SECURITY DEFINER with empty search_path; owner-bound program/outbox relations and hashed approval tokens inherited from 018. Consent scopes separate Coach/Reflect with exact Coach policy; Activation, grant, live term, optimistic program version, quiet hours, selected days, late window and unanswered limit rechecked before dispatch. Claimed deliveries reclaim only with fresh token; dispatched crash becomes uncertain and cannot replay. Shared budget comes from profile, not caller limits. New Reminder insertion/cancellation triggers participate in same budget transaction. Program purge retains consumed content-free capacity while deleting program/outbox content.

Findings reported and corrected before this proof:

- optional program reservation lock must precede participant budget lock (FK/key-share deadlock ordering);
- local reservation replay must also compare program identity;
- consumed Coach reservations must survive program deletion via nullable program FK;
- pending legacy rows with delivery attempts/provider message IDs must retain consumed debt, ahead of pristine-pending classification;
- canonical Activation must gate enqueue/dispatch, including fixture parity;
- author SQL Activation fixture required canonical Reminder intended date/time/timezone columns.

Fresh isolated PostgreSQL 15 proof: `/tmp/amigo-review019.py`, using role bootstrap then migrations001–019 (20 SQL files). Source 019 copied into the new cluster directory before application and exact SHA printed. Cluster `/private/tmp/amigo-review019-lr6bnpll`, port55519, stopped after proof. No Supabase; no existing database reset.

Exact successful output:

```
019 source SHA256: 06e51e050c60a8247d21498ee6ce582cee09f1d38b77d781d360756f91d2e760
PASS legacy six commitments incl pending-attempted/accepted retained; four overflow debt; pristine cancelled excluded
PASS fresh bootstrap + migrations001-019: 20 SQL files
PASS 019 roles, withdrawal-before-dispatch, claim fencing + reclaimed stale worker probes
PASS Reminder replacement/Later refusal atomic rollback; unsent cancel releases; attempted cancel retains debt
PASS independent expired/stale approval, optimistic version, exactly-once completion, raw receipt denial probes
PASS concurrent eight independent PostgreSQL reservations: exactly four admitted/four refused
PASS mixed actual Coach enqueue vs four Reminder reservations: four admitted/one refused
19|1|0
```

Final program count1 is the explicit committed synthetic mixed-concurrency fixture; lifecycle/proactive/Reminder assertions use rollback transactions. Final entries0 expected for the directly seeded synthetic active program. The stopped disposable cluster contains only reviewer fixtures.

Reminder probes compare original Reminder bytes, Task bytes/version, outbox count, receipt count, total Reminder count and original reservation after both rejected replacement and rejected Later. All unchanged. Unsent cancellation releases capacity; dispatched cancellation preserves it. Legacy pre019 fixtures cover pristine pending, pending attempted, pending with accepted message ID, sending, sent, cancelled attempted and cancelled pristine; six count, four overflow entries debt, pristine cancelled excluded. Eight independent concurrent SQL connections admit exactly four reservations; separate five-way race between real Coach enqueue and four Reminder reservations admits exactly four overall.

Exact driver and SQL probes retained in `019-independent-probes/` beside this record (original /tmp basenames; driver references those /tmp paths). File digests:

- `amigo-review019.py`: `d27f84b47d13ca34b2e3b321c8ed0361f6a85dc411ce23f7561c584ab6331d27`
- `amigo-review019-extra.sql`: `91f4be949c305c1eabb94b08f661cdd2da7d3c87761ae629d21fd7c41f1a7373`
- `amigo-review019-reminders.sql`: `042c37cb6385645fdee1692bc784b0ff4ad0ac1efd115818f16df878523384ad`
- `amigo-review019-legacy-seed.sql`: `d17fae1e92e5d508226a03b732818b436d44d7bea5b47b0babca718ed405e93d`
- `amigo-review019-legacy-assert.sql`: `c69fabea8dbfea8ab54894117d70f1dfa6e0984e1fd259a60b4ce871348809ed`
- `amigo-review019-mixed-seed.sql`: `b952513329e50b122bd3c22b5a8e9a7dc58ca274b62efbdc38643ecbea304be9`
- `amigo-review018-extra.sql`: `13d37fa239714baac03270a9e53148a9448e91226cf99e2c3fa413ae66e7a488`

Python integration evidence: 96 focused tests passed across real Coach application boundary, delivery worker, Store contracts, Reflect and candidate suites; Ruff clean on new application tests. This record certifies reviewed SQL semantics and local fictional proofs, not live provider results, deployment, or privacy readiness. All specialized Modes remain subject to default-deny admission until explicit readiness approval.

Verdict: no unresolved blocking SQL019 finding at this exact source hash. Worker kill recheck is tracked separately with author; later SQL changes require re-verification.
