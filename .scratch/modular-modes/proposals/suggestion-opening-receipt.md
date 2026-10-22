# Confirmed suggestion opening receipt (review finding 19)

The service-only confirmation transaction rechecks opt-in, an active required grant,
owned open Daily source/control Sessions, pending Handoffs, and pending Coach approvals.
It selects or creates an owned Session fixed to the target Mode and records that Session
with the source and newest Daily control Session. Both Daily selectors change in the
same transaction. No source Message, context summary, or carried request is copied.

Provider conversation creation follows the database commit. A five-minute claim lease
fences concurrent callbacks; a known provisioning failure releases that claim so the
same Open button can retry the same logical Session. A crash permits an explicit retry
after lease expiry. Every retry rechecks guards and rejects a newer Daily control
Session, a changed selector, a closed target, an opt-out, or a revoked grant. Completion
is fenced before the opening notice; an uncertain notice is not automatically resent.
This is a logical Session guarantee, not a provider exactly-once creation guarantee.
No target model Turn runs during any confirmation or opening retry.

All Store implementations expose claim_mode_suggestion_opening(user_id, offer_id),
release_mode_suggestion_opening(user_id, offer_id, claim_token), and
complete_mode_suggestion_opening(user_id, offer_id, claim_token). The first returns
None, {status: busy}, or {status: claimed, offer: owned receipt}; the others return a
boolean. Claim tokens and Session identifiers remain internal controller metadata.
Direct service-role table reads and private-helper EXECUTE are revoked; application
reads and writes use owner-filtered RPCs. Readiness remains required at the application
boundary before confirmation and immediately before publication.
