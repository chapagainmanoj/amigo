# Internal Preflight Evidence

Gate A remains **not passing** until one manifest for the exact staging release passes
`scripts/validate_preflight_evidence.py` and its linked artifacts survive independent review.
The checker implements the minimum evidence and ownership contract from the approved release-gate
decision; it does not run deployments or manufacture evidence.

## Capture procedure

1. Record one full Git commit SHA, Render deployment ID, UTC interval, operator, and the dedicated
   staging environment. Do not mix revisions or production/participant traffic.
2. Record exactly one always-on Render backend, scheduler owner, and Telegram webhook destination;
   Fly must be inactive and Telegram, Supabase, dashboard, and model resources must be separate.
3. Attach passing backend/frontend CI, clean migration/RLS, model evaluation, isolation,
   fail-closed configuration, replay, ambiguous-time, restart, readiness, delivery, lateness,
   public-surface, and independent-security evidence. Every record needs a distinct producer and
   reviewer, real UTC observation time inside the release interval, matching revision,
   environment and deployment ID, plus a relative artifact path and verified SHA-256. The release
   implementer may produce evidence and may review a record produced by someone else, but nobody
   may review their own record. The release implementer cannot approve the required independent
   security review. Use canonical lowercase stable actor IDs—not display names—for every producer,
   reviewer, operator, implementer, founder, and witness field.
   The model-evaluation record additionally links the archived full last-passing Gate A run and
   its comparison, which binds both finalized run artifacts by SHA-256. The comparison reviewer
   must be the record reviewer and must explicitly review subjective tone and every derived new
   failure pattern. Its UTC review time must be inside the release interval, cannot be in the
   future, and participates in the ordering that requires the founder decision to be strictly
   later than all reviewed evidence.
4. Run the clean-account Dashboard Account → Pairing → Task → Reminder → Done → dashboard path
   three consecutive times. Use distinct, strictly ordered run IDs and artifacts, hash-chain each
   trial to its predecessor, and record no lost, duplicate, or cross-participant effect.
5. Record zero open Critical and Gate-A High findings. The founder then records an explicit pass
   or fail decision; the founder cannot be the required independent security reviewer.

Validate the assembled JSON manifest:

```bash
python scripts/validate_preflight_evidence.py --template > evidence/internal-preflight.json
# Replace every placeholder with independently reviewable evidence, then validate:
python scripts/validate_preflight_evidence.py evidence/internal-preflight.json
```

The checker reads artifacts relative to the manifest, verifies their bytes against the recorded
digests, and rejects path traversal. Missing, unknown, invalid/reversed/future/out-of-window,
mismatched, duplicated, unchained, self-reviewed, baseline-free, comparison-free, or non-passing
evidence returns a non-zero exit status and lists every blocker. A passing manifest proves only
Gate A for that exact release; it does not authorize Gate B or external invitations.
The linked Gate A validator also recomputes call/result integrity, canonical state hashes and
multi-turn chaining, execution usage/cost, and final totals; malformed JSON or unreadable manifest
bytes return a clean nonzero blocker rather than a traceback.

The runtime workload and thresholds remain defined in
[`staging-performance-evidence.md`](staging-performance-evidence.md), and the model artifact rules
remain defined in [`model-evaluation.md`](model-evaluation.md).
