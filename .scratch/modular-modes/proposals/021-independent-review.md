# Issue05 / 021 independent review

Scope: current worktree versus fixed HEAD 48a164f508110e762070154795648d54a9fe9fc3;
Issue05, build-plan Phase6, decisions14/23/28 and provisional Issue05 contract. Review by a separate
implementing agent from the Issue05/021 author. No production, secret or provider access.

## Standards

Application-layer offer and confirmation logic preserves the Store boundary and uses the neutral
channel API; no Telegram imports or model-side effects were added. Three Stores expose matching
narrow methods. SQL021 uses owned reads, RLS, revoked client/direct service mutation, hardened
SECURITY DEFINER RPCs and the complete001–020 prerequisite guard. No new Daily Tool or instruction.

## Spec

Two concrete parity findings resolved by the author during review:

- Local create/resolve previously required the latest Daily Session whereas SQL accepted any
  owned open source Session. Local owned-session lookup now matches SQL. Regression covers older
  open Sessions alongside a newer open Session; confirmation still executes no target Turn.
- Local create accepted `grant_required=None` for an ungranted target; SQL rejects NULL. Reproduced
  pending offers in both local Stores. Local and MemoryStore adapter now reject non-Boolean grant
  flags, and the adapter rejects non-Boolean confirmation before PostgreSQL coercion.

Added regression evidence: `pytest tests/test_mode_suggestions.py -q` →54 passed in1.16s across
InMemoryStore, FakeStore and MemoryStore RPC double. Covers older owned open Session, pending Coach
approval, expired approval, NULL/non-Boolean confirmation nonconsumption, invalid grant flags, and release-readiness alone failing the default-deny clearance gate.
`pytest tests/test_gate_a_currency.py -q` →111 passed in5.76s. Targeted Ruff passed.

The authored lexical crisis rule is additional suppression only. Offers remain default OFF and
require a separate default-deny per-Turn clearance seam; no authoritative clearance provider,
release/friction evidence or decision23/28 approval is claimed by passing these tests. Existing
application tests prove no preconfirmation target Session and empty target transcript after open.

## Fresh independent SQL proof

Command: `.venv/bin/python /tmp/amigo-review021.py`; retained source in
`021-independent-probes/amigo-review021.py`. Unix-socket-only disposable cluster
`/private/tmp/amigo-review021-_o5s5_ed`, port55531, owner mano; stopped after verification.
Actual bootstrap+all001–021 migrations applied to a fresh cluster;021 assertions passed.
This was not the CI legacy-seed chain or a complete020 behavior review (separately assigned).

Eight independent concurrent SQL creates returned exactly one offer; eight confirmations returned
exactly one confirmed receipt. An older owned open Daily Session remained valid beside a newer
open one. No Coach Session was created by confirmation. Extra probes passed: NULL confirmation
does not consume; pending Coach approval blocks offer; expired approval permits it; closed source
Session refuses confirmation. Initial extra fixture omitted required Program state; corrected to
explicit draft before successful rerun. No migration defect was masked by that fixture correction.

Verified SHA256:

- 020_durable_memory.sql:
  `ff6dd9e533b8db76d242ce95b78168499cfeddc23e776a3aab266b0c0c90f52d`
- 021_confirmed_mode_suggestions.sql:
  `7c515d31f4ef93417fc1c382c50d350affcc168d40ed4540394cf7fa02b652ec`
- assert_021_confirmed_mode_suggestions.sql:
  `210dce4eadd3fc68693cc24bc05ae6e18ccbba480fd6dff4f6ea42b20c0a381d`

Result: no remaining blocking Standards or Spec finding within this scope after the two parity
fixes. Release remains default OFF. Real clearance provider and decisions23/28 evidence remain
unmet admission prerequisites. This review proves database single-use resolution, not transactional
atomicity of an external channel send or crash recovery of opening a confirmed Mode conversation.

After this run020 changed to `273f33cc8a383c1b7362798721cedf2d07a67d07b44b59fd77e9bd346922481b`.
The frozen applied020 in the retained cluster matches the ff6dd9 hash above;021 and its assertions
remain byte-identical to the verified hashes. Parent must run the final combined current chain;
this report does not claim validation of later020 edits.

Final root combined currency check: actual45-file CI SQL chain reapplied to a new local database
amigo019_full_22bc146ce3 after020 froze at273f33cc…. All45 passed, schema21 missing-chain/predecessor
guards passed, Activation forced interleave/30trials155calls passed. Exact current hashes retained
in phase6-chain-verification.md;021 independent bytes unchanged. This closes the older020-hash
caveat for the final combined chain without rewriting historical independent-probe results.
