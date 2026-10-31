# ADR 0007: Retire the Telegram-only identity paths

## Status

Accepted as a direction (owner, 31 October 2026). **Blocked:** it starts only after production runs on
schema 24 code, and nothing below is built yet.

## Context

ADR 0004 kept Telegram byte-compatible through several legacy paths:
- the `user_profiles.telegram_chat_id` column, plus a trigger that mirrors it into `channel_identities`;
- the v1 functions `complete_pairing`, `claim_telegram_update`/`finish_telegram_update` (with the 009 claims
  table) and `finish_reminder_delivery`;
- `reminders.telegram_message_id`.

The v2 functions still *delegate* to the v1 functions for Telegram, so nothing can be dropped yet. The code
also still reads the legacy column in these places:
- the one-query inbound lookup (`get_user_by_chat_id`);
- the full-access check (`access.is_full_access_user`);
- the Later context join;
- the Activation "delivered" predicate (013), through `telegram_message_id`.

## Decision: retire in three releases, each its own migration and deploy

1. **Code moves off the legacy reads (no schema change).**
   - Full access becomes a check on channel identities: is the Telegram identity on the list?
   - The Later context join drops the column.
   - The Activation predicate and delivery proof use `channel_message_ref` and `delivery_channel`.
   - The inbound lookup reads `channel_identities` (one query, an indexed unique key).
2. **Migration 025: the v2 functions stop delegating.**
   - Telegram Pairing, update claims and delivery are written in the v2 functions themselves, against
     `channel_identities` and `channel_update_claims`.
   - Claims still pending in the 009 table are copied over. The 009 table becomes read-only and is
     dropped a release later.
   - The v1 functions are revoked from `service_role`.
3. **Migration 026: drop the mirror trigger, `telegram_chat_id` and `telegram_message_id`.**

## Preconditions

- Production runs schema 24 code.
- At least one release cycle with no Telegram regressions.
- Owner approval of each migration after its independent review (AGENTS.md).

## Consequences

- Each step can be reverted on its own. The column is dropped last, so steps 1 and 2 can be rolled back.
- The local Stores (`src/memory/identities.py`) lose their Telegram special cases in the same releases.
