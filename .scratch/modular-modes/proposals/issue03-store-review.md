# Issue 03 Store review — 22 October 2026

Scope: seven Mode/grant/handoff APIs in MemoryStore, InMemoryStore, FakeStore and
src/memory/modes.py; migration 016 is the SQL contract. Historical slice: `44956f1^...44956f1`
(`44956f1 Handoffs created`); current bytes inspected. Review skill applied on two independent
axes. This review does not certify unbuilt application routing or execution recovery.

## Standards

Independent reviewer: PASS; no concrete violations found.

- Matching asynchronous Store APIs across all three implementations.
- Supabase access inside MemoryStore; owner-filtered reads.
- Trusted grant flags supplied by application adapters, returned state detached.
- Serialized local expiry, grant-cap and confirmation transitions.
- Single-use confirmation; nonconfirmations omit carried request; no execution in Store.

Standards sources: AGENTS.md, CONTEXT.md, docs/architecture.md, ADRs 0001/0002.
`tests/test_mode_store_contracts.py`: **67 passed in 0.06s**.

## Spec

Independent reviewer: PASS; no actionable findings in reviewed seven APIs.

- DTO fields/statuses match 016.
- Trusted grant flags persist; resolution rechecks grants.
- Reads filter owner; resolution binds participant and Session.
- Fourteen-day maximum, five-grant cap, audit and expiry revalidation mirrored.
- Serialized confirmation single-use; decline/expiry/unavailable do not return carried payload.

Compared Issue 03, application proposal, build-plan Phase 2 and adopted migration 016.
`tests/test_mode_store_contracts.py`: **67 passed in 0.06s**.
Adapter coverage uses RPC/query doubles; no new PostgreSQL execution is claimed.

## Crash injection

`tests/test_handoff_crash_window.py`: **2 passed in 0.02s**, against InMemoryStore and FakeStore.

Injected application failure immediately after successful resolve_handoff confirmation and before
any target execution. The committed Session switched to Daily. A replay returned only
`{"status":"unavailable"}` and could not recover the carried request through resolve_handoff;
no target Turn or Task ran. The simulated callback failure preserves Store state, modelling the
committed transition; local Stores themselves do not survive a process restart.

**Confirmed gap:** 016 persists confirmation, not execution intent/claim/completion. Phase 4 must
close it before target execution is wired. Claim/lease alone does not establish exactly-once Tool
side effects after a crash following Tool commit; crash tests must cover those boundaries too.
No production data, migrations or SQL bytes changed in this review.

Summary: Standards 0 findings; Spec 0 findings. Known confirmation/execution gap reproduced,
deferred to the explicitly approved Phase 4 design.
