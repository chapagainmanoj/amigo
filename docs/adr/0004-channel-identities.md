# ADR 0004: Channel identities and a primary channel

## Status

Proposed — 30 October 2026. Migration 022 is written but not applied. Owner review is required before Store work.

## Context

Mode conversations are already channel-neutral (ADR 0003), but participant identity is not.
`user_profiles.telegram_chat_id BIGINT UNIQUE NOT NULL` is the only identity key. Pairing, update
claims, Reminder delivery proof and the outbox payloads all carry Telegram ids. As a result, a second
messaging app cannot hold a participant, and one participant cannot use two apps.

## Decision

- **Identity is `user_id`.** Each messaging app links through a `channel_identities` row
  `(user_id, channel, external_id TEXT)`. The `(channel, external_id)` pair is unique, and each participant
  has at most one identity per channel. External ids are opaque provider identifiers. They never become
  participant identity, and the dashboard API never returns them.
- **One primary channel.** `user_profiles.primary_channel` selects where proactive messages
  (Reminders, recovery summaries, Coaching nudges) go; `src/channels/delivery.py` holds the rule.
  It must name a channel the participant has linked (deferred foreign key). The participant chooses it
  on the dashboard; the choice is shown only when more than one channel is linked. Handoff replies and
  notices stay with the conversation's own channel. Crash recovery of a handoff is unprompted, so it
  follows the primary channel, like a Reminder. Handoffs do not record their channel (provisional,
  31 Oct 2026).
- **The recipient is resolved at delivery time** from the primary channel's identity. Outbox payloads stop
  being the source of the recipient. The drain passes the legacy `telegram_chat_id` key only as a
  scheduling hint, which delivery overrides, and migration 023 removes it from the producers.
- **Second-app Pairing reuses the dashboard token.** The signed-in dashboard issues the existing single-use
  token. The new app's adapter calls `complete_pairing_v2(token, channel, external_id)`, which links to the
  token's existing user, or creates the user if this is their first app. Identity is proven only through the
  dashboard, never through another messaging provider.
- **Telegram stays byte-compatible.** `telegram_chat_id` remains and is dual-written. A trigger mirrors it
  into `channel_identities`, so the legacy RPCs and the Store keep working during the transition. For
  `channel = 'telegram'`, the v2 RPCs delegate to the existing Telegram RPCs, so update claims and Pairing
  locks keep their current tables and semantics across the deploy.
- **Delivery proof** becomes `channel_message_ref TEXT` on Reminders. Telegram also writes
  `telegram_message_id`, which keeps the Activation delivery predicate (migration 013) correct while
  Activation stays Telegram-only.

## Consequences

- Production remains Telegram-only. Decision 16's demand and release gates still govern any new
  production channel. This ADR only removes the identity barrier.
- Participant Turns serialize by `user_id`, not by chat, so two apps cannot run concurrent Turns for one
  participant.
- The schema gate is exact-match. Once 022 is applied, old instances refuse to start, and new code
  refuses to start before it. Apply the migration and deploy back to back.
- Until the code moves to the v2 RPCs, v1 `finish_reminder_delivery` routes through v2, so every
  Telegram delivery also records `delivery_channel` and `channel_message_ref`.
- Code still reads `telegram_chat_id` in several places: the 013 Activation `paired` check, the 017
  handoff listing, the scheduler join, and the `later` and Activation outbox payloads. Profiles without
  Telegram (created only by `complete_pairing_v2`) are not production-ready until those reads move to
  channel identities.
- Migration 023 removes the outbox payload key from the three producers (006, 008, 013) and the
  `telegram_chat_id` column from the 017 handoff listing. A later migration retires the legacy RPCs,
  the dual-writes and, eventually, `telegram_chat_id`, once production runs on the v2 RPCs.
- Telegram-only on purpose, not transition debt: the full-access allowlist
  (`access.is_full_access_user`, configured as Telegram chat ids), Telegram `/start` Pairing in
  `bot/pairing.py` (other adapters call `complete_channel_pairing`), the Activation "telegram" step,
  and `smoke_check.py --channel`.
- Other apps join only an existing, activated, full-access account (owner decision, 31 Oct 2026).
  Pairing on them never creates a profile, and full access stays an owner list of Telegram chats,
  so there are no full-access accounts without Telegram.
- Identity rows are deleted with the profile (`ON DELETE CASCADE`). Data exports do not list them,
  because external ids are never returned to the dashboard.
