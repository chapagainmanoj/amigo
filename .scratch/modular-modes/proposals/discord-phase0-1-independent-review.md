# Independent review: Discord Phases 0 and 1 (e32f456, fef29b8, e55e68a) and the Discord adapter plan

Reviewer: independent subagent, 31 Oct 2026. Read-only. I made no tracked-file edits, no billed runs, no network, no Supabase.
Probes and throwaway copies are in the session scratchpad
(`/private/tmp/claude-501/-Users-mano-Workspace-amigo/9c87b9c4-4f74-408d-9acc-9e50bf0280b7/scratchpad/`).

## Verdict

- **Blockers for merging Phases 0/1 as they are (production registers only Telegram): none.** I verified that the Telegram
  hot path, the pairing statuses and the copy are unchanged (§A1).
- **Should-fix before Phase 2. Treat these as Phase 2 blockers, because they go live the moment a second adapter is registered:**
  - S1: the registered/invite posture admits every registered account on non-Telegram apps. The owner decision says "full-access only".
  - S2: non-Telegram `/pair` redeems any token, including the Telegram deep-link token, and so creates Discord-first profiles. After
    that, `/api/pairing-token` returns 409, so the account can never pair Telegram.
  - S3: handoff recovery can execute or retire rows on the wrong channel when the primary channel is not registered. `main.py` wires
    recovery only for the Telegram controller.
  - S4: the dashboard Mode switch (`main.py:_open_mode`) and the maintenance jobs are still bound to the Telegram adapter.
  - S5: Discord-only accounts can never be full access (`access.py:35`).
- **Nits:** N1–N7 below.

## Commands run

| Command | Result |
|---|---|
| `python -m pytest tests/ -q` | `1819 passed in 21.02s` |
| `ruff check src tests scripts` | `All checks passed!` |
| `python scripts/smoke_check.py --scheduler` | `scheduler: in-memory APScheduler reminder fired through channel` |
| New Phase 0 tests run against `e32f456^` (git archive in scratchpad) | 4/4 behaviour tests FAIL on old code, so they are meaningful |
| New Phase 1 registry tests run against `e32f456` with the registry module copied in | 3/5 FAIL on old wiring. The 2 pure registry unit tests pass, as expected |
| `PYTHONPATH=. python scratchpad/probe1.py` | Output quoted in the findings |

## A. Code review

### A1. Telegram behaviour unchanged (verified, no finding)
- **Query count and shape.** `MemoryStore.get_user_by_channel_identity("telegram", s)` (`src/memory/store.py:167-176`) calls
  `get_user_by_chat_id(int(s))`. That is the same single `user_profiles.eq(telegram_chat_id)` query, and the pattern guard
  `TELEGRAM_ID_PATTERN` matches every real Telegram chat id. Inbound counts are unchanged:
  - `_hold_inbound` already used it before Phase 0 (`git show e32f456^:src/bot/update_claims.py:119`);
  - `_is_allowed` (registered) makes 1 lookup;
  - `handle_message` makes 1 lookup;
  - `ReminderActions` makes 1 lookup.
  The only difference is in logs (N3).
- **Pairing statuses.** For Telegram, `complete_pairing_v2` (`migrations/022_channel_identities.sql:153-155`) validates and then
  `RETURN public.complete_pairing(p_token, p_external_id::BIGINT)`. The statuses are therefore identical to v1 (015/022):
  `invalid_token`, `already_paired`, `conflict` (including `unique_violation`), and `paired`. No other statuses exist. The Python
  `validate_identity` pre-check only rejects ids Telegram never sends, such as 0.
- **Local Stores.** `LocalIdentityState.complete_pairing` (`src/memory/identities.py:187-243`) keeps the v1 Telegram branch, which
  reads `telegram_chat_id`. InMemoryStore and FakeStore delegate to it identically.
- **Copy.** `display_name="Telegram"` reproduces the exact old strings: "Telegram is connected.", "Successfully paired! Telegram
  is connected…", and "…or Telegram profile is already linked…".
- **Protocol.** `display_name` is added on `TelegramChannel`, `CLIChannel` and `FakeChannel`. Both `FailingChannel`s subclass
  `FakeChannel` (`tests/test_reminders.py:11`, `tests/test_scheduler.py:114`). This meets the AGENTS.md requirement.
- **Gate A.** `src/channels/registry.py` was added to `INVALIDATING_INPUT_PATHS` (`src/evaluation/gate_a.py:87`). `src/access.py`
  is already listed. `tests/test_gate_a_currency.py` is untouched; its last commits are 0defbc7 and c77bdce.
- **Test fixtures.** None of the fixture changes weakens an assertion.
  - `link="fake"` in `test_modes.py`, `test_mode_routing.py` and `test_coaching_application.py` adds an identity that the old
    handlers silently did not need.
  - `test_cli_seed.py` and `test_cli_preview.py` switch to `channel_id="cli"` to match the CLI-only fixture, and they still assert
    that Activation completes.
  - `test_pairing.py` only renames tests. `test_bot_handler_routes_pairing` still drives `/start pair_` through `BotHandlers`.

### S1 (should-fix, Phase 2 blocker). The registered posture admits any registered account on non-Telegram apps
`src/bot/handlers.py:233-244`: the `registered`/`invite` branch returns before the non-Telegram check runs, so the
"full-access only" rule applies only in `allowlist`.
```
registered, non-full-access, discord allowed: True      <- probe P2
allowlist,  non-full-access, discord allowed: False
```
The owner decision (plan, "Access is limited to full-access accounts") and AGENTS.md (Discord is a new processor, and decision 04
or the privacy promise must be updated before any non-owner participant uses it) both require the restriction in every posture.
Production runs `registered`.
**Fix:** in `_is_allowed`, after `open`/`closed`, put `if channel_id != "telegram": return pairing-ok-for-full-access-only…`
ahead of the registered branch. Add a test for registered plus non-Telegram plus a trial account.

### S2 (should-fix, Phase 2 blocker). Non-Telegram `/pair` creates Discord-first profiles and locks the account out of Telegram
- `handle_pairing` calls `complete_channel_pairing` for any channel.
- The non-Telegram branch of `complete_pairing_v2` (022:189-194) **creates** a profile when the token's account has none.
- Today the only tokens that exist are the ones `/api/pairing-token` issues for *unlinked* accounts, inside a `t.me/...start=pair_<token>`
  link. A participant who copies that token into a Discord DM therefore gets a Discord-first account.

The plan calls that out of scope, but nothing enforces it. The consequences:
```
reply: 🎉 Successfully paired! discord is connected ...                 <- probe P1
profile created: True primary: discord telegram_chat_id: None
=> /api/pairing-token now 409s (get_user_by_auth_id truthy): True    (src/api/pairing.py:38-39)
activation step: profile paired: True completed: False
```
- The account can no longer pair Telegram. The dashboard 409s with "Dashboard account is already linked.".
- The account can never be full access (S5).
- Activation continues on Discord. The SQL 013 predicate also accepts `provider_accepted_at`, so it can probably complete; verify
  this on staging.

In `allowlist`, non-Telegram pairing attempts are admitted for anyone (`handlers.py:240-242`), but Telegram pairing attempts are
not (probe: `allowlist, telegram unlisted, pairing_attempt allowed: False`).

**Fix options, smallest first:**
- (a) In `handle_pairing`, for `channel_id != "telegram"`, refuse unless the token's account already has an activated, full-access
  profile. This needs a store read of the token's owner, or a v2 flag `p_require_existing`.
- (b) Channel-scoped tokens: add a `pairing_tokens.channel` column, with v2 rejecting a mismatch. This needs a migration and
  subagent migration review.

Either way, the Telegram deep-link token must not be redeemable off Telegram.

### S3 (should-fix). Handoff recovery semantics with a registry
`src/handoffs.py:218-222` `_recovered_elsewhere`:
- **Primary not registered.** This happens when Discord is disabled, failed at boot, or runs in a CLI-only process. The method
  returns False, so the controller acts on its own channel. That contradicts the registry contract ("None … then this process
  never sends", `registry.py:11-12`):
  ```
  telegram controller executed on Telegram (not primary): True            <- probe P4
  discord-only row retired as: endpoint_unavailable                         <- terminal; Discord process could have run it
  ```
  A Discord-primary participant's confirmed handoff is either run and answered on Telegram, or **permanently retired**. It is not
  left pending for when Discord is back.
- **Two controllers registered.** `main.py:83-85` wires only `handlers.handoffs.recover` (the Telegram controller). With Discord
  registered, Discord-primary rows are skipped forever by the Telegram controller:
  `only-telegram-controller recovery with discord registered -> executed: 0 retired: 0 (row left pending)`.
  Phase 2 must call `recover` on every channel's controller. A single registry-aware recovery routine would be better.
- **No double execution.** `claim_handoff_execution` fences execution, so double execution is not possible.
- **Unresolved channel question.** ADR 0004 says "Handoff replies and notices stay with the conversation's own channel", but
  recovery uses the *primary* channel. The review queue notes this is provisional because handoffs do not record their channel. A
  handoff confirmed on Discord whose participant's primary is Telegram is recovered on Telegram. Decide this, and preferably record
  `channel` on the handoff when it is confirmed.
- **Missing tests:** primary unregistered; recovery wiring for two controllers.
- **Fix:** when `self.channels.for_user(user) is None`, `return` (leave the row pending). Do not fall through to retirement.

### S4 (should-fix before Phase 5). Paths still bound to the single Telegram adapter
- `src/main.py:158-164` `_open_mode` uses `channel.recipient_for(user)` and `handlers.turn_processor`, both Telegram.
  - For a Discord-primary user without Telegram, `/api/modes/{id}/open` returns 409 "Connect Telegram first"
    (`src/api/modes.py:179-180`).
  - With Telegram linked, the Mode opens on Telegram, not on the primary channel.
- `main.py:94-97` maintenance:
  - `close_expired_modes` uses only the Telegram handler's `ModeConversationService`. `_close_unavailable` skips rows where
    `row["channel"] != self.channel.channel_id` (`src/conversations.py:85`). Discord rows are never closed. This is harmless while
    Discord has `threads=False`, but it is latent.
  - The handoff recovery problem is covered in S3.
- `ReminderScheduler.channel` stays as `channels.default`, and it is used only as a `_delivery_proof` fallback. That is OK.
- Inbound-scoped objects are correct per `BotHandlers`, because inbound replies belong on the inbound channel:
  - `ReminderActions`, `CoachingController`, `MemoryController` and `ModeSuggestion`;
  - `ToolContext.channel` and `CommandContext.surface=deps.channel.channel_id` (`src/tools/toolsets.py:75…`).
- `CoachingDeliveryWorker.reconcile` has no channel dependency. `drain_once` correctly resolves `(channel, recipient)`
  (`src/scheduler/coaching.py:170-229`).

### S5 (should-fix, document now). Discord-only accounts can never be full access
`access.is_full_access_user` reads only `telegram_chat_id` (`src/access.py:35-36`), and the allowlist is Telegram ids
(`is_full_access_user(discord-only): False`, probe P3). Taken together with S1 and S2:
- in `allowlist` such an account is locked out;
- in `registered` it gets a trial (`trial_finished_message` quotes a Discord snowflake as the "reference", and the owner cannot
  allowlist it);
- CBT research Mode is unreachable for it.

This is acceptable only if S2 makes Discord-first impossible. Otherwise full access needs to be keyed by `user_id` or by
`(channel, external_id)`.

### Nits
- **N1.** `handoffs.py:222` compares adapters by identity: `primary is not self.channel`. Compare `channel_id` instead, so that
  wrapped or re-instantiated adapters do not silently match "elsewhere".
- **N2.** `scheduler/reminders.py:390-421` has a pre-existing race that is now multi-channel. `channel` is resolved before
  `claim_reminder_for_send`. If the primary switches between the claim and `_daily_delivery`, `_daily_delivery` raises
  "Reminder channel is not the participant's primary channel" *after* the claim. The Reminder is then recorded as a failed
  `do_not_retry` attempt with `delivery_channel` = the old channel, which never tried. The Reminder is lost. Low probability;
  consider releasing the claim instead.
- **N3.** On Supabase, each Telegram lookup now logs two `database_operation=` lines, because the `@_observe_database_call` methods
  are nested (`store.py:166-174`). Metrics built from these logs double-count on the inbound path.
- **N4.** `pairing_token` (`src/bot/pairing.py:14-24`) changes behaviour:
  - Telegram text `/pair <x>` and leading-whitespace `/start pair_…` are now pairing attempts. In the registered posture they bypass
    `_is_allowed`, and the result is only the "invalid link" reply.
  - Near-misses fall through to a model Turn, which sends the token to Gemini and stores it in session history:
    `'/pair_<tok>'`, `'/pair:<tok>'`, `'/pair<tok>'`, `'/PAIR <tok>'`, a bare 32-hex token, and `'/pair@Bot <tok>'` all give
    `None`. Consider short-circuiting any message that contains a 32-hex run to the invalid-link reply.
  - Multi-line `/start pair_<tok>\nhello` gives the malformed-token reply, the same as before. `/pairing` gives None, which is
    correct.
- **N5.** `FakeChannel.display_name` falls back to the raw id ("discord is connected"). That is fine for fakes; the real adapter
  must set "Discord".
- **N6.** `ReminderScheduler(channel=registry)`: the parameter name is misleading.
- **N7.** Test gaps:
  - `_is_allowed` in registered/invite for non-Telegram (S1);
  - Telegram typed `/pair`;
  - handoff recovery with the primary unregistered (S3);
  - recovery summary and Coach nudge delivery on a non-default registry channel (only `_send_reminder` is covered);
  - delivery proof on error paths for fake2.

## B. Plan critique (`discord-adapter-plan.md`)

Platform facts I am confident about are stated plainly. The ones I am not sure of are marked **verify**.

### B1. Hosting: the gateway inside the Render web process. Highest feasibility risk
- **Free plan sleeps.** `render.yaml:8` is `plan: free`, and `main.py`'s lifespan comment confirms idle spin-down ("must stay wakeable
  by Telegram"). Render free web services spin down after about 15 minutes without *inbound HTTP* (verify the current Render
  policy). An outbound gateway websocket does not keep the service awake.
  - While the instance sleeps, Discord DMs never reach Amigo, and nothing wakes it.
  - After a fresh IDENTIFY (not a RESUME), Discord does not replay missed MESSAGE_CREATE events, so those messages are lost.
  - **Decision needed:** paid always-on instance, keep-alive, or a startup backfill. A backfill would read each linked DM channel's
    history after the last processed message id, deduped via `channel_update_claims`.
- **Rolling deploys.** Two instances overlap, and each opens its own gateway session with the same token. Both receive the same
  MESSAGE_CREATE. `claim_channel_update` dedupes on `(channel, message.id)`, so this is safe, but write a test for it. Only one
  process should *send* proactively; the existing scheduler owner lease covers that.
- **Event loop.** Use `await client.start(token)` in a task, never `client.run()`, which owns the loop and installs signal handlers.
  On shutdown, `await client.close()` before `reminder_scheduler.shutdown()`. Gateway heartbeats share the loop with Turns:
  - a long synchronous stall (more than the heartbeat interval, about 41 s) drops the session;
  - `monitor_event_loop_delay` already exists; alert on it.
- **Memory.** Free instances have 512 MB. Use minimal intents (`dm_messages` only, not `guilds`/`members` beyond what DM delivery
  needs), set `member_cache_flags=none`, and use a small `max_messages`.
- **Fail-closed rule.** The plan says "fail closed in production only if Discord is enabled". Define what happens when Discord is
  *registered* but disconnected at fire time. Today a send exception becomes `do_not_retry`, so the Reminder is lost. And if the
  adapter is not registered, Discord-primary Reminders sit pending with no log or fallback (`reachable_here` skips them in
  `reconcile`).
  - Add a dashboard or health signal.
  - Decide whether delivery stays strictly primary-only (ADR 0004) or falls back to another linked channel when the primary adapter
    is down.

### B2. Intents and DMs
- **Message content.** DM content to the bot does not require the privileged Message Content intent. The non-privileged
  `DIRECT_MESSAGES` (`dm_messages`) intent is still required; add it to the plan.
- **Ignore list.** Ignore `author.bot`, including the bot itself (a DM's MESSAGE_CREATE fires for the bot's own sends), guild
  messages, MESSAGE_UPDATE, and attachment-only or empty-content messages.
- **DM reachability for proactive sends.** A bot can DM a user only if they share a server, or the user has installed the app (user
  install; verify that it permits bot-initiated DMs). The user must also not have blocked or disabled DMs from server members.
  - If the user leaves the server, sends fail with "Cannot send messages to this user" (error 50007; verify the code).
  - Map that error to a terminal, visible delivery failure: `ConversationUnavailableError`/`endpoint_unavailable`, not a
    silent loss. Surface "Discord can't reach you" on the dashboard.
- **DM channel resolution.** `recipient_for` returns a user id, but sending and editing need the DM channel id.
  - `fetch_user` plus `create_dm` is 2 REST calls per proactive send.
  - Cache the DM channel id (discord.py caches private channels per session), or store it in the identity row's metadata. External
    ids must still never reach the dashboard.

### B3. Interactions, the 3-second ack and the coordinator
- **Ack timing.** `ChannelUpdateCoordinator.run` (`src/bot/update_claims.py:76-80`) awaits `claim_channel_update`, a Supabase RPC
  from Render, before `acknowledge()`. Cold starts, Supabase latency or a busy loop can exceed Discord's 3-second window, and the
  user then sees "This interaction failed".
  - Discord does not redeliver interactions, so claiming first buys nothing.
  - Ack (defer) in the adapter on receipt, or add a coordinator option that acks before the claim.
- **Defer type.** For component (button) interactions, use a deferred *update* (type 6, no "thinking…" state), not a deferred
  channel message (type 5). Verify discord.py's `response.defer()` default for components; I believe it is a deferred update unless
  `thinking=True`.
- **Ids.** `update_id = interaction.id` and `message.id` are both snowflakes, so they are globally unique and do not collide in
  `channel_update_claims (channel, update_id)`. Neither the Telegram claims table nor `channel_update_claims` has pruning. Note the
  growth.
- **Gateway resume.** RESUME replays only events after the last sequence. Duplicates are rare but possible; the claim handles them.

### B4. Buttons
- **`custom_id` length.** Discord allows at most 100 characters. Every current format is under Telegram's 64-byte limit, so
  everything fits:
  - `done:/skip:/later:<uuid>`;
  - `mode:<id>`;
  - `memory:<ctl>:<hex32>:<ver>`;
  - `coach:<a>:<hex32>[:<v>]`;
  - `suggest:yes:<uuid>`;
  - `handoff:c:<b64>:<b64>` (about 54 characters);
  - `consent:<ver>`.
- **Uniqueness.** `custom_id`s must be unique within one message. They currently are.
- **Layout.** Discord allows at most 5 buttons per action row and 5 rows. `/mode` puts *all* entitled Modes in one row
  (`src/bot/modes.py:57-68`), and Telegram allows up to 8 per row. The adapter must **re-chunk** rows rather than reject them, and
  define what happens past 25 buttons. Button labels are limited to 80 characters.
- **Editing old buttons.** `edit_message_buttons(chat_id, message_id)` needs the DM channel id (B2). Editing Telegram-era buttons
  from Discord never happens, because callbacks are channel-local.

### B5. Text and ids
- **Splitting.** Discord's content limit is 2000 characters.
  - Split on paragraph or line boundaries, never inside a surrogate pair or a code fence.
  - Return the *last* part's id, the one with the buttons, as the delivery proof. Document that parts 1..n-1 are not proof.
  - Telegram never splits (no 4096 handling in `telegram.py`), so very long replies already behave differently across channels.
- **Rendering.** Telegram sends plain text (no `parse_mode`). Discord renders Markdown in plain content: `*`, `_`, `#`, `>`, and
  backticks in model output will format. Also send with `allowed_mentions=AllowedMentions.none()`.
- **Id types.** `IncomingUpdate.message_id: int | None` and the `send_message -> int | None` return hold snowflakes as Python ints;
  that is fine. `channel_message_ref = str(id)` is fine. `Recipient` should be `str(author.id)` everywhere, as the plan says, so that
  `recipient_matches` and identity lookups compare equal.

### B6. Typed commands
- **Typed `/mode`.** I believe the desktop and mobile clients send typed `/mode` text as a plain message when the user does not pick
  a registered command from the picker. The picker UX pushes users toward registered commands. Verify this in the spike.
- **Registered slash commands.** If you register `/pair`, `/mode`, `/daily`, `/help`, `/memory` and `/program`, they arrive as
  **interactions**, not messages.
  - They need ack plus a follow-up, and have a 15-minute token window. Long model Turns must reply through the follow-up webhook or a
    normal DM send.
  - The decoder must synthesise `kind="message"` text with `update_id = interaction.id`.
  - Registering `/pair` as a slash command also keeps the token out of the visible DM history.

### B7. Pairing UX and the 409
- **The 409.** The plan correctly identifies it (`src/api/pairing.py:38-39`). The new endpoint should issue
  **channel-scoped tokens** (fixes S2). It should require an activated, full-access account (fixes S1 and S5), and it must keep the
  existing rate limits.
- **Without that fix, the designed path cannot be used.** Until Phase 3, the only redeemable tokens belong to unlinked accounts, so
  the only Discord pairing that works in today's code is the out-of-scope Discord-first path.
- **Activation stays Telegram-only.** Keep `step="telegram"` copy. With S2 fixed, Discord-first cannot occur.

### B8. Privacy, decision 04, routing and Gate A
- **Privacy and decision 04.** Discord becomes a processor of message content. AGENTS.md requires a stop before any non-owner
  participant. S1 currently would admit any registered participant once the adapter is registered. Make `DISCORD_ENABLED` plus a
  full-access check in all postures a hard invariant, with a test.
- **Data export and deletion.** Identity rows cascade on profile deletion. Messages stored on Discord's side are outside Amigo's
  deletion promise. The privacy text must say so.
- **Model routing.** Unchanged. Coach and Daily routing do not depend on the channel. Confirm that nothing keys `MODE_MODELS` or pins
  by channel.
- **Gate A.**
  - `src/channels/discord.py` is reachable from `main.py` but not from the Turn path. Add it to `INVALIDATING_INPUT_PATHS` anyway, as
    the plan says, since it shapes inbound text (splitting and decoding).
  - The Phase 0/1 edits to `handlers.py`, `pairing.py`, `reminders.py`, `coaching.py` and `handoffs.py` are hashed inputs, so Gate A
    evidence is stale again. The review queue says the owner reruns it.
  - Daily instructions and the Tool schema are untouched (verified: no prompt or toolset diffs in e32f456 or fef29b8).

### B9. Recommended plan changes (summary)
1. Before Phase 2: fix S1 (full-access-only in every posture for non-Telegram channels) and S2 (no first-app creation or
   Telegram-token redemption off Telegram; channel-scoped tokens or an existing-profile requirement). Add tests.
2. Phase 1 follow-up:
   - handoff recovery leaves rows pending when the primary is not running (S3);
   - `main.py` runs `recover` and `close_expired` for every registered handler;
   - `_open_mode` resolves the participant's primary adapter and that adapter's `BotHandlers` (S4);
   - decide handoff channel semantics, preferably by recording the confirming channel.
3. Phase 2 additions:
   - the `dm_messages` intent;
   - ignore self;
   - ack before claim for interactions, using a deferred update;
   - re-chunk buttons to 5×5;
   - Markdown-safe 2000-character splitting with `AllowedMentions.none()`;
   - cache DM channel ids;
   - map "cannot DM" to a visible terminal failure;
   - `client.start`/`close` in the lifespan.
4. Hosting decision before the owner spike: free-plan sleep means lost DMs. Choose always-on or add an on-start history backfill
   per linked DM.
5. Define behaviour when the primary adapter is registered but disconnected, or not registered (pending vs fallback vs visible
   failure). Today it is silent.
6. Spike checklist additions:
   - typed `/mode` delivery as plain text;
   - bot-initiated DM to a user-install-only user;
   - the 50007 path after the user leaves the server;
   - a rolling-deploy overlap with two gateway sessions;
   - a restart during a Discord Turn.
