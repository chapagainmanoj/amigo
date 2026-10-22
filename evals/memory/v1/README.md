# Memory fictional retrieval fixture v1

Run `.venv/bin/pytest tests/test_memory_retrieval_eval.py -q`.

Seventeen fixed fictional cases compare exact retrieved item IDs against expected sets using
`InMemoryStore.read_memory_context`, including scope/owner exclusion, explicit sharing,
Reflect exclusion, inactive/completed/cancelled state, 90/180-day confirmation intervals,
explicit validity, separate pause controls, relevance, ranking and the three-item limit.
Each returned item must carry an untrusted marker and a use disclosure; its use ledger is checked.

This deterministic lexical fixture establishes regression evidence for these cases only.
It does not certify semantic sensitive-content eligibility, general retrieval accuracy,
participant demand, privacy readiness, or trial admission. Admission remains disabled by default.
No provider calls, participant content or secrets are used.
