# Telegram Topics as Mode conversations

**Status: Accepted — 22 October 2026.** Owner spike passed on Telegram Desktop and iOS.
**Android was not tested** (no device). This accepts the channel-neutral amendment below;
production topic mode must remain off until Phase 4 is deployed and reviewed.

## Decision

Mode identity, authorization, Sessions and handoffs are channel-neutral. Telegram topics are one
channel capability, not the canonical Mode model. A `ConversationRef(channel, endpoint)` addresses
a linked conversation; only `TelegramChannel` interprets Telegram thread IDs. Channels declare
capabilities, including `threads`, and an explicit fallback (decision 16).

On threaded channels, the incoming conversation selects the Mode. Unknown conversations route to
Daily and are remembered as additional Daily endpoints, preserving the reply location. A Mode
can therefore have several conversations. On channels without threads, `/mode`, `/mode <id>` and
`/daily` are the main entry mechanism; Telegram also retains these commands for older clients.
Both paths use one Mode resolver, with the same entitlement and `(user_id, mode_id)` Session rules.

`mode_conversations` holds the canonical endpoint per participant/Mode/channel, with primary key
`(user_id, mode_id, channel)` and unique `(channel, endpoint)`. Additional endpoint aliases preserve
unknown Daily conversations without replacing the canonical endpoint used for proactive delivery.
Aliases are channel-neutral too. For Telegram, an endpoint contains chat and thread IDs.

Every message to a topics-enabled chat carries an explicit conversation. This includes pairing,
access/Activation errors, feedback, Turn replies and Reminders. Messages lacking an incoming
conversation resolve/create the canonical Daily conversation before sending. Reminders resolve
Daily on the primary messaging channel at delivery time; outbox payloads do not gain thread IDs.

Startup checks the bot capability settings. Topics off uses in-chat Mode commands, including
in production, with a warning. Production refuses only when topics are on and user-created
threads are also on; an unavailable user-created flag is warned about. Outside production, a failed capability check warns and leaves
the non-threaded command path available. No threadless resend is permitted in a topics-enabled chat.

Handoffs remain participant-confirmed and treat carried requests as untrusted. History stays
isolated by Mode Session. Closing expired/revoked Mode conversations preserves history; deleting
a Telegram topic is not a stop, mute or grant-revocation operation.

## Owner spike evidence — 22 October 2026

- Private topic creation worked; `getMe.has_topics_enabled` was true.
- Desktop initially showed no tabs until updated/reopened. Sending from “New Chat” created an
  unknown incoming thread (225 rather than created 223).
- Desktop and iOS rerun replies arrived in created thread 227. Android **not tested**.
- Sending without a thread succeeded and created a new topic. Consequently all bot sends must
  use an explicit thread. This behavior with user-created threads disabled remains untested.
- Sending to deleted thread 227 returned `ok:true` and restored the topic. Routing and recovery
  must not depend on “message thread not found”; any defensive error path must keep an explicit
  conversation and must never resend without a thread.
- Disabling “Allow users to create new threads” in BotFather made
  `allows_users_to_create_topics` false and removed “New Chat”. Bot-created topics still worked
  (thread 235).

These are owner-reported observations, not builder-run live API tests. Tokens/chat contents were
not copied into the repository. See the [spike runbook](../../.scratch/modular-modes/proposals/topic-spike-runbook.md).

## Alternatives

- One shared chat with Mode commands: retained as the main path on channels without threads;
  threaded channels additionally provide visible conversation separation.
- One bot per Mode: rejected; multiple tokens/pairing flows and linked endpoint complexity.
- Participant-created forum groups: rejected; unnecessary setup and different privacy context.

## Consequences and remaining checks

Migration 017 adds neutral conversations/aliases, Mode-scoped Sessions and durable handoff
execution state. All Store implementations and channel implementations must match. Independent
migration review and local SQL verification precede repository adoption; no Supabase application
is authorized. Dashboard links use the bot chat rather than invalid private-topic `t.me/c` links.

Android interoperability and threadless-send location after disabling user-created threads are
unverified. They do not justify threadless sends or block the owner's accepted Phase 4 design.
