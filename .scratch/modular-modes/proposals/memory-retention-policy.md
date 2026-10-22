# Memory retention: review fix 14

Status: implementation policy, owner review; participant admission remains OFF.

The owner chose the documented-policy option in review item 14. Expiry and supersession stop
retrieval immediately but do not start a new deletion timer: the exact versions remain visible
in the Inspector until the participant chooses Forget or turns Memory off. This preserves the
version-history contract. Active, inactive and needs-confirmation records follow the same
participant-controlled deletion boundary. No automatic seven-day version-history purge is added.

Forget immediately clears the selected item's plaintext and provenance across all its versions,
removes its use ledger, deletes every confirmation claim belonging to that participant, and nulls
every owned receipt payload hash, including the current Forget receipt. Receipt results contain
only references, settings or content-free status metadata; they contain no preview/content digest.
Save/correction receipts whose hashes were scrubbed cannot replay; scoped Forget retries return
only their existing content-free status. Outstanding process-local previews are cleared by the
application. Content-free item/version tombstones remain visible; turning Memory off physically
deletes all saved versions, claims and uses as decided in fix 13.

Periodic `MemoryService.prune()` removes process-local expired candidates and invokes the Store's
service-only `purge_memory_claims()` RPC. Expired and consumed durable claims are deleted even
when admission is OFF. Live claims remain until confirmation, expiry, Forget or withdrawal.
This maintenance does not delete saved version history, conversation Messages or Session summaries.

Decision 13 requires Forget deletion from active systems within seven days and propagation through
backups within the existing 30-day privacy window. This implementation removes active plaintext
immediately; it does not operate, verify or promise erasure of PostgreSQL/WAL/provider backups.
The 30-day backup requirement remains an operator verification task and a readiness blocker.
No published privacy notice, retention promise or participant admission is changed by this policy.
