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

The v2 functions still *delegate* to the v1 functions for Telegram, so nothing can be dropped yet.

Python still reads or writes the legacy fields here (review of 7deb2d6, S2):
- `telegram_chat_id`:
  - the one-query inbound lookup (`get_user_by_chat_id`), also used by `scripts/grant_mode.py` and
    `smoke_check.py --channel`;
  - the Telegram delivery address (`TelegramChannel.recipient_for`);
  - `store.create_user`, which inserts it;
  - the full-access check (`access.is_full_access_user`);
  - the Later context join;
  - the outbox drain hint (`scheduler/outbox.py`), which old outbox rows may still carry.
- `telegram_message_id`:
  - read by the Activation "delivered" check (`src/activation.py`, `src/memory/activation.py`) and the
    proactive budget (`src/memory/proactive.py`);
  - written by the scheduler's delivery proof (`scheduler/reminders.py`).
- Dead v1 Store wrappers with no callers outside `src/memory/`: `claim_telegram_update`,
  `finish_telegram_update` and `complete_pairing`.

SQL still uses them too:
- `schedule_reminder_command` (023) selects `telegram_chat_id`;
- the Activation predicate in `get_activation_state` and `create_activation_test_command` (013) read
  `telegram_message_id`;
- `finish_reminder_delivery_v2` writes `telegram_message_id`.

## Decision: retire in three releases, each its own migration and deploy

1. **Python moves off the legacy reads (no schema change).**
   - Full access becomes a check on channel identities: is the Telegram identity on the list?
   - The Later context join and the outbox hint drop the column.
   - The inbound lookup and `TelegramChannel.recipient_for` read `channel_identities` (one query, an
     indexed unique key). `create_user` writes the identity, and the mirror runs the other way.
   - The local Activation and budget mirrors use `channel_message_ref` and `delivery_channel`.
   - The dead v1 Store wrappers go.
2. **Migration 025: the database moves off them, and the v2 functions stop delegating.**
   - The Activation predicate (013) and `schedule_reminder_command` are redefined against
     `channel_message_ref`, `delivery_channel` and `channel_identities`. `finish_reminder_delivery_v2`
     stops writing `telegram_message_id`.
   - Telegram Pairing, update claims and delivery are written in the v2 functions themselves, against
     `channel_identities` and `channel_update_claims`.
   - Claims still pending in the 009 table are copied over. The 009 table becomes read-only and is
     dropped a release later.
   - The v1 functions are revoked from `service_role`. In the same change,
     `scripts/check_activation_lock_order.py` moves to `complete_pairing_v2`, because CI runs it as
     `service_role`.
3. **Migration 026: drop the mirror trigger, `telegram_chat_id` and `telegram_message_id`.** Its
   verification block checks that no function body still names either column.

## Preconditions

- Production runs schema 24 code.
- At least one release cycle with no Telegram regressions.
- Owner approval of each migration after its independent review (AGENTS.md).

## Consequences

- Each step can be reverted on its own. The column is dropped last, so steps 1 and 2 can be rolled back.
- The local Stores (`src/memory/identities.py`) lose their Telegram special cases in the same releases.
