# Discord adapter plan: the multi-app proof (owner and internal accounts only)

Status: proposal, 31 Oct 2026. The owner asked for it in conversation. Decision 16 still says No Expansion Yet for
production, and this plan does not change that. Discord stays off by default and owner-only until the privacy
promise and decision 04 are updated.

## Goal
One participant uses Telegram and Discord on the same Amigo account:
- pairs Discord from the dashboard,
- chats on either app and gets the reply on that app,
- has Turns serialized across both apps,
- chooses Discord as the primary channel, and then Reminders, recovery summaries and Coach nudges arrive on
  Discord only.

## What exploration found (blockers before any Discord code)
1. **The shared bot layer is still Telegram-keyed.**
   - `store.get_user_by_chat_id` (a Telegram lookup) is called in `src/bot/handlers.py:89,155,227`,
     `src/bot/reminder_actions.py:76`, `src/conversations.py:51` and `src/bot/pairing.py:62`.
   - Pairing calls v1 `complete_pairing(token, chat_id)`. Telegram's `/start pair_` deep link is hard-coded.
   - The allowlist reads `ALLOWED_TELEGRAM_CHAT_IDS`. User-facing text says "Telegram".
   - The CLI only works because its dev user is also a Telegram user.
2. **The scheduler, outbox worker and Turn lock are single-process.**
   - `ParticipantTurnSerializer` is an in-memory lock. `SCHEDULER_OWNER_KEY="beta-scheduler"` and the outbox worker
     assume one owner.
   - A second Discord process would steal outbox effects and break the cross-app Turn lock.
   - → Run Discord **inside the existing web process**. That is two channels in one process, so the deferred
     `ChannelRegistry` is now justified (review-queue decision: "add the registry when two channels share a process").
3. **The dashboard can't issue a second-app token.** `POST /api/pairing-token` returns 409 when the account is already
   linked (`src/api/pairing.py`). The "Connect another app" button was never built.
4. **Activation's "telegram" step stays Telegram-only.** For the proof, Discord is a *second* app on an already
   activated account. Discord as a first app is out of scope.

## Phases (each: tests, ruff, scheduler smoke check, review-queue entry)

### Phase 0: channel-neutral bot layer (no Discord yet; it is worth doing on its own)
- `BotHandlers`, `ReminderActions`, `ModeConversationService.ensure_by_chat` and pairing resolve the sender with
  `store.get_user_by_channel_identity(channel.channel_id, str(chat_id))`.
  The Telegram behavior and its Supabase round trips stay the same (the 022 RPC delegates).
- Pairing becomes `handle_pairing(channel, chat_id, token)` → `store.complete_channel_pairing`. Each adapter decodes
  its own pairing syntax: Telegram `/start pair_<token>`, Discord `/pair <token>`, and it passes a neutral pairing intent.
- `_is_allowed` per channel:
  - Telegram keeps its allowlist.
  - Other channels accept only senders linked to a full-access account. `access.is_full_access_user` already
    resolves through the mirrored `telegram_chat_id`, so owner accounts qualify.
- Copy: "Telegram" → the channel's display name (`channel.display_name`).
- The CLI dev fixture stops depending on a Telegram identity (it pairs `cli` only).
- `MessageChannel` gains `display_name`. Per AGENTS.md, update Telegram, CLI, FakeChannel and both FailingChannels.

### Phase 1: `ChannelRegistry` (two channels in one process)
- `src/channels/registry.py`: `{channel_id: channel}`.
  - `for_user(user)` returns the primary channel's adapter, or None when that channel is not in this process.
  - It replaces `reachable_here(channel, user)`.
- `ReminderScheduler`, `CoachingDeliveryWorker` and `HandoffController` take the registry. Proactive sends resolve the
  adapter at fire time. Inbound replies and handoff notices keep the conversation's own channel.
- One `ChannelUpdateCoordinator` per channel sharing **one** `ParticipantTurnSerializer`. One `BotHandlers` per channel
  sharing the store, session manager and scheduler.
- With one channel registered, behavior is byte-identical. Keep the Telegram key snapshot test.

### Phase 2: `src/channels/discord.py` (the adapter)
- Library: `discord.py` (gateway). Free-text DMs need the gateway; the HTTP interactions endpoint covers only slash
  commands and buttons. Content of DMs to the bot doesn't need the privileged message-content intent.
- Started as an asyncio task in `lifespan` when `DISCORD_ENABLED` is set; stopped on shutdown. If it fails, the
  Telegram webhook keeps working. Fail closed in production only if Discord is enabled.
- **DMs only**: guild messages and other bots are ignored.
- Capabilities: `threads=False` (Discord has no threads in DMs), so Modes use the in-chat command fallback.
  - `actions=True`: buttons are message components, each button's `custom_id` taken from our button data.
  - `message_editing=True`, `deep_links=False`.
- `IncomingUpdate`:
  - Messages: `update_id = message.id`, `chat_id = str(author.id)`.
  - Button presses: `kind="callback_query"`, `update_id = interaction.id`, and `acknowledge = interaction.response.defer()`
    to meet Discord's 3-second ack.
- `send_message`:
  - Splits text at 2000 characters (Telegram allows 4096). Buttons go on the last part, at most 5 per row and 5 rows.
  - Returns the message id (snowflake int).
  - `channel_message_ref = str(id)`.
- `recipient_for`: the user's `discord` identity row. `recipient_matches` compares strings. Opens the DM with
  `fetch_user(id).create_dm()`.
- Outages and rate limits: rely on the library's 429 handling. No extra retry loops (AGENTS.md).

### Phase 3: pairing UX (dashboard)
- API: `POST /api/channels/{channel}/pairing-token` for an already linked, activated account.
  - Same rate limits and expiry as today. Returns the token plus instructions.
  - Registered only when the channel is enabled.
  - `GET /api/channels` gains `available` (enabled channels not yet linked).
- Web: a "Connect another app" control in `PrimaryChannel.jsx` showing:
  - a bot invite/DM link (`DISCORD_APPLICATION_ID`),
  - the command to copy, `/pair <token>`,
  - and a refresh of the linked list. After that, the primary-channel choice appears (2+ apps linked).

### Phase 4: config, docs and gates
- `src/config.py` (protected; list it): `DISCORD_ENABLED=false`, `DISCORD_BOT_TOKEN`, `DISCORD_APPLICATION_ID`.
  `runtime_config` checks a token is set when Discord is enabled.
  The owner sets `.env`; I never touch it.
- `pyproject.toml`: `discord.py`.
- Docs:
  - AGENTS.md env table.
  - `docs/architecture.md` (new-channel recipe: registry now exists).
  - ADR 0004 (adds Discord as the multi-app proof).
  - A runbook for creating the Discord app.
- Gate A: add `src/channels/registry.py` / `discord.py` and any newly reachable modules to `INVALIDATING_INPUT_PATHS`.
  Daily instructions and Tool schema stay unchanged.

### Phase 5: proof tests (offline, no Discord network)
- Adapter unit tests with fake discord.py objects: decode, ack, text splitting, button mapping, guild and bot messages ignored.
- Cross-app end-to-end on FakeStore with Telegram + Discord fakes in one registry:
  - pair Discord as the second app,
  - a Turn on each app gets its reply on that app,
  - simultaneous Turns serialize,
  - switching the primary to Discord moves Reminders to Discord only, with delivery proof `delivery_channel=discord`,
  - a Reminder button tap on the old Telegram message still resolves idempotently.

### Phase 6: owner spike (STOP; needs the owner)
- The owner creates the Discord application and bot, puts the token in `.env`, adds the bot to a private server
  (for DM reachability), and pairs.
- Checklist: Telegram + Discord chat, `/mode` fallback, Reminder on Discord, switching the primary back, the
  restart/recovery summary.
- Before any non-owner participant: privacy promise + decision 04 update (Discord as a processor). AGENTS.md stop.

## Open questions to verify in the spike
- Can a bot DM a user who shares no server with it? (Assumption: no, so the runbook uses a private server.)
- Does the Discord client send typed `/mode`-style text as plain text when no slash command matches?
  If not, register a few slash commands that map to the same text.

## Out of scope
- Discord in guild channels.
- Voice.
- Discord as a first app (Activation stays Telegram).
- Production rollout.
- Retiring v1 RPCs.

## Owner decisions (31 Oct 2026)
- Discord runs in the same web process, behind a `ChannelRegistry`.
- Access is limited to full-access accounts, and Discord is off by default (`DISCORD_ENABLED`).
- Start Phase 0 now. Stop for review after Phases 0 and 1.

## Changes after the independent review (31 Oct 2026; `discord-phase0-1-independent-review.md`)
- Fixed before Phase 2: S1–S5. See the review queue.
- Hosting:
  - `render.yaml` is the free plan, which sleeps when idle. An outbound gateway connection neither keeps it awake nor wakes it.
  - Phase 6 needs always-on hosting (owner cost decision), or Discord DMs sent while it sleeps are lost.
- Phase 2 adapter:
  - Interactions: acknowledge with a deferred update *before* the claim RPC (Discord's limit is 3 seconds). The coordinator needs an
    "ack first" option.
  - Buttons: re-chunk into at most 5 per row and 5 rows (`/mode` puts every Mode in one row). `custom_id` lengths are fine.
  - Intents: `dm_messages`. Ignore the bot's own messages. Cache DM channel ids. Turn off mentions in sends.
  - Errors: map "cannot send to this user" (verify the error code) to a visible delivery failure.
  - Splitting: split at 2000 characters without breaking Markdown, and record the last part's id as proof.
  - Gateway resume can redeliver messages, and channel update claims deduplicate them by message id. Verify
    `claim_channel_update` semantics for non-Telegram channels in all three Stores.
- Pairing: the dashboard endpoint for a second app should issue channel-scoped tokens, only to full-access
  accounts (Phase 3). The bot side already refuses everything else.
- Decide in Phase 2: when the primary channel's adapter is down or not registered, Reminders and recovery wait pending, and
  nothing warns the participant. Add an operator-visible signal.
- Spike checks to verify:
  - whether typed `/mode` arrives as plain text;
  - whether the bot can DM a user who installed the app but shares no server;
  - whether two gateway sessions overlap during a rolling deploy.
