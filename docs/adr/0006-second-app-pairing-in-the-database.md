# ADR 0006: Second-app Pairing never creates an account, enforced in the database

## Status

Accepted. The owner approved it on 31 October 2026. Migration 024 is written but not applied.

## Context

Pairing on an app other than Telegram must only link an existing, activated account (ADR 0004; review
finding S2). Today the bot enforces this in two steps: `get_pairing_token_owner`, then
`complete_channel_pairing`. That makes it a check-then-act, and the rule lives outside the function that
creates profiles. The database function `complete_pairing_v2` itself still creates a profile when the
token's account has none. Any other caller, such as a future adapter or a script, can therefore create an
account whose only app is not Telegram, and that account can never pair Telegram afterwards.

## Decision

- Migration 024 changes `complete_pairing_v2` for every channel except `telegram` and `cli`. If the token's
  dashboard account has no profile, or its Activation is not complete, the function returns
  `{"status": "account_required"}` without consuming the token. It never inserts a profile for those
  channels.
  - "Activation complete" means `activation_journeys.completed_at` is set (013), the same record the bot
    checks through `get_activation_state`. `user_profiles.onboarding_complete` is not used, because the
    legacy bot onboarding set it for profiles that never had a dashboard Activation.
  - The rule runs before `already_paired` and `conflict`, so an account that is not activated gets
    the same answer whatever its links are.
  - Telegram keeps creating profiles through Activation, as before.
  - `cli` is the local development app: it only ever runs on the in-memory Stores, and it is the first app
    for its fixture. The exemption is safe in the database because only `service_role` may call the
    function.
- InMemoryStore and FakeStore mirror the same rule.
- The full-access part of the rule stays in the application (`access.may_use_channel`). Full access is
  owner configuration (`ALLOWED_TELEGRAM_CHAT_IDS`), not data, so the database can't enforce it.
  `get_pairing_token_owner` therefore stays.
- The bot maps `account_required` to the same refusal it sends today. Nothing else reads the status yet.

## Consequences

- Schema 24. Apply it after 023 is live, and deploy matching code right after, as with every migration.
- The invariant "non-Telegram apps never create accounts" holds for every caller, not only the bot.
- The check before acting still exists for full access. The token's owner cannot change between the two
  calls, so it is safe.
