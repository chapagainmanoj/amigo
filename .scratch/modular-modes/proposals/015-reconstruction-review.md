# Reconstructed 015 — ordered pairing locks

Status: adopted in the repository after owner approval and independent review; not deployed
Prepared: 2026-10-03

The old temp directory and its SQL/assertion artifacts are missing. These are newly reconstructed
bytes based on migration 003 and the documented corrections in the old review record. Original
hashes, approval, and old concurrency/mutation results do not certify these files.

The reconstruction preserves migration 003's token checks, both identity-conflict decisions,
adoption/new-profile handling, unique-violation mapping, consumption, and idempotent re-pairing.
It adds the documented per-row candidate lock loop ordered by user_id and retains both original
locked re-reads. Service-only execution and empty search_path remain. A structural verification
earns ledger015 rather than blindly inserting it, but independent concurrent execution is still
required to prove the deadlock fix.

Adoption is not authorized. Review/test on a fresh isolated001–014 chain, then apply this015 and
its assertions. The approved repository, application expected schema14, and production remain
unchanged. Once separately approved,015 must precede016; update the gate, CI chain, schema SQL
assertions, README/docs, and Activation-vs-pairing concurrency probe together.

SQL chain and rollback assertions passed on a fresh isolated PostgreSQL15 database against the
approved001–014 chain, followed by current016 and its assertions. The pairing assertions seed
synthetic token rows as database owner to isolate this function from013's Activation issuance gate.
Independent static review preserves migration003's decisions and locked re-reads. The persisted
`probe_015_016_concurrency.py` now independently reproduced a crossed-pairing deadlock using
the original003 function (one deadlock) and eliminated it using these reconstructed015 bytes
(zero deadlocks; both crossed requests return `conflict`). An observational advisory gate is
injected after the first identity-row lock, both workers are observed waiting in
`pg_stat_activity`, and only then is the blocker released. The original fixture function is
restored in `finally`; generated identities/tokens are removed. This certifies the new proposal
bytes for this concurrency scenario, not the lost original artifact or production adoption.

New review bytes (not the old lost hashes):

- 015 SQL SHA-256: `55cac11a14e03a8be4cba13c107994a2fe17f6fb31e67bffb53028d5d676fdae`
- Assertions SHA-256: `c5a3f8dd850bda1966df80ec17f11a8aca295fc218637b72aee0dc898f7ae80e`
