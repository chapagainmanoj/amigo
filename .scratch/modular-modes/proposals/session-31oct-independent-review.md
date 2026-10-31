# Independent review: session 31 Oct 2026 (`3d5808d..20dd82e`)

Reviewer: independent subagent. Scope: 17 commits. The focus was Discord Phases 2–5 (`c4768a9`, `680abaf`, `2a2f21d`, `51f6f2c`,
`20dd82e`). I re-checked the S1–S5 fixes (`d20ee81`) and the interactions with the 023 work. I modified no tracked files, used no
network, and ran no billed model. The probes are in
`/private/tmp/claude-501/-Users-mano-Workspace-amigo/9c87b9c4-4f74-408d-9acc-9e50bf0280b7/scratchpad/probes/`.

## Verdict

- **Blockers: none.** Discord is off by default, and the Telegram webhook path is byte-identical. Nothing ships to participants.
- **Should-fix, before or during the Phase 6 owner spike** (SF1–SF6). Each one would distort a spike checklist result or
  contradicts a written claim:
  - SF1: the gateway task can die silently.
  - SF2: when Discord fails to start or isn't logged in yet, Reminders for Discord-primary participants are **permanently
    failed**, not left pending.
  - SF3: shutdown and rolling deploys drop in-flight Discord Turns.
  - SF4: a failed `defer()` drops the button press.
  - SF5: a slow Discord login blocks app startup, Telegram included.
  - SF6: Discord is offered to *every* full-access account, but policy says owner/internal only.
- **Nits:** N1–N9.

## Commands run (all green)

| Command | Result |
|---|---|
| `python -m pytest tests/ -q -p no:cacheprovider -o faulthandler_timeout=30` | `1842 passed in 11.51s` |
| `ruff check src tests scripts` | `All checks passed!` |
| `python scripts/smoke_check.py --scheduler` | `scheduler: in-memory APScheduler reminder fired through channel` |
| `python scripts/run_gate_a_eval.py --validate-only` | `validated amigo-gate-a-v1: 60 cases, 3 repetitions` |
| `cd web && npm run lint && npm run build` | lint clean; `✓ built` (only the existing >500 kB chunk warning) |
| `git diff --stat 3d5808d..HEAD -- src/agent src/tools tests/test_gate_a_currency.py evals` | empty: Daily instructions, Tool schema and the currency test are untouched |
| `git diff 3d5808d..HEAD -- tests \| grep '^-\s+assert'` | 3 removed asserts, each replaced by an equal or stronger one (dict gains `available`, stub moved to a per-channel dict) |

## Verified correct (no finding)

**discord.py 2.7.1 API.** I read the installed source and ran probe `p_discordpy.py` against real objects with no network:
- `Client(intents=Intents.none()+dm_messages, allowed_mentions=AllowedMentions.none())` can be built outside a running loop. This
  matters because `main.py` builds it at import. Output: `intents: 4096 dm_messages True message_content False guilds False`.
- `@client.event` inside the builder registers `on_message` and `on_interaction` (`True True`).
- `ConnectionState.parse_interaction_create` (state.py:814-831) dispatches to the ViewStore and then **always** fires
  `on_interaction`. A real component payload reached `on_update` as `('callback_query', '555', 'done:r1', True)`. A DM reached it
  as `('message','555','hello',False)`. The bot's own message was ignored.
- ViewStore: `View(timeout=1)` is stored on send (`abc.py:1709`). It is removed about 1 s after `_start_listening_from_store`:
  `view store after send: [777]`, then `after 1.2s: [] finished True`.
  - A click inside that 1 s runs the default `Button.callback`, a no-op that never responds (`ui/view.py:587-600`).
  - A click after it gets no item lookup.
  - Either way, our `defer()` is the only response, so there is no double response and no "interaction failed".
- `View.__init__` tolerates a missing loop (`ui/view.py:243-248`). `PartialMessage.edit(view=None)` sends `components: []`
  (`http.py:194-204`).
- `defer()` on a component interaction is `deferred_message_update` (`interactions.py:875-879`).
- `interaction.id` and `message.id` are `int`. `guild_id` is `None` in DMs.
- `close()` on a client that never logged in is safe (P9).

**Group 1 (023) interactions.**
- `get_reminders_for_reconciliation` selects `user_profiles(primary_channel)` (`store.py:1713`), so the registry routes correctly
  on Supabase too.
- No remaining `int(chat_id)` or `telegram_chat_id` in shared Discord-reachable paths, apart from the documented Telegram-only
  `access.py` and the `outbox.py:49` hint.
- `/mode`, a button tap (`mode:coach`), `/program` and `/memory` all work on Discord's `threads=False` (probe
  `p_modeflow.py`: `buttons: ['mode:coach', 'mode:reflect', 'mode:recommender', 'mode:cbt']`, then the list is cleared and Coach
  opens).

**Group 2 S-fixes.**
- S1 (`handlers.py:236-242`): other apps require a linked full-access account in closed, allowlist and registered. Caveat: N1.
- S2 (`pairing.py:30-42,56`): Pairing needs a live token whose account exists, is activated and has full access.
  `get_pairing_token_owner` exists in all three Stores (`store.py:1850`, `memory_store.py:1778`, `fakes.py`).
  - Token reuse: a Phase-3 token redeemed by another Telegram chat gives `conflict`, because `identities.py:227` refuses when the
    auth user's `telegram_chat_id` differs. No takeover through the Telegram deep link.
- S3: `_recovered_elsewhere` leaves rows pending when the primary is unregistered, compares `channel_id`, and every controller
  recovers.
- S4: `_open_mode` and Mode expiry use the primary channel or every channel.
- S5: documented in ADR 0004.

**Telegram path.**
- The `/webhook` function is not in the diff.
- `ChannelUpdateCoordinator.run` with `acknowledge_first=False` keeps claim-then-acknowledge.
- `initialize`, `decode_update` and `acknowledge_callback` are called only on the Telegram adapter (`main.py:138,296,329`).

**Protocol.** `DiscordChannel` implements every `MessageChannel` member, `display_name` included. AGENTS.md lists it.

**Dashboard API** (`src/api/channels.py`):
- Gated by `get_activated_user`. The full-access check is on the *fresh* profile.
- A uniform 404 for not-full-access, not-enabled, already-linked and `telegram`/`cli`, so nothing leaks.
- `Cache-Control: no-store`. No external ids are returned (test asserts).
- CORS and middleware are unchanged.
- `issue_pairing_token` (013) has no "already linked" refusal, so the Supabase path works like the fakes.

**Web** (`PrimaryChannel.jsx`):
- `app_link` is server-built from config only (`discord.py:251-258`). It renders as `href` with `target=_blank rel=noreferrer`
  (`noreferrer` implies `noopener`).
- No `dangerouslySetInnerHTML`. React escapes `command`. The path segment is `encodeURIComponent`-encoded. React 19 also blocks
  `javascript:` URLs.

**Gate A.**
- `src/channels/registry.py` was added to `INVALIDATING_INPUT_PATHS`.
- `discord.py` is imported only by `main.py`, like `telegram.py`. It is not a Turn module and the currency test passes.

## Should-fix

### SF1. A dead gateway is silent. `src/channels/discord.py:171-188`
`start()` keeps `self._task = asyncio.create_task(self.client.connect(reconnect=True))` and attaches no done-callback.
- `Client.connect` re-raises fatal closes: `PrivilegedIntentsRequired` for 4014, `LoginFailure` / `ConnectionClosed` for 4004, and
  others (`client.py:739-775`).
- The task holds the exception. Because we keep a reference, asyncio never logs "exception was never retrieved".
- `close()` then swallows it (`contextlib.suppress(asyncio.CancelledError, Exception)`).

Probe `p_failures.py`:
```
P2 gateway task done: True exception: PrivilegedIntentsRequired
P2 (no log line above = the gateway died silently; Telegram/health unaffected)
P2 close() suppressed it
```
Inbound Discord stops with no log. `/health` stays ok.

**Fix:** `self._task.add_done_callback(...)` that logs `logger.error("Discord gateway stopped: %s", type(exc).__name__)` for
anything but cancellation. Optionally expose it in `/ready` as a non-gating field.

### SF2. Discord-primary Reminders are permanently failed, not pending, when Discord isn't logged in. `main.py:63-66,147-167`; `reminders.py:387-421`
- `discord_channel` is added to the registry at import, whatever `start()` later does. `for_user` therefore returns the Discord
  adapter, and `_send_reminder` **claims** the Reminder before `send_message` fails.
- If login failed, or hasn't happened yet, `send_message` raises inside `_dm()` (`fetch_user` → HTTP with no session or token).
  The failure is recorded as `error` / `do_not_retry`.
- Startup order makes this a race even with a good token: `initialize_runtime` starts the scheduler, the outbox and
  `reload_pending` (`main.py:139`), and recovery summaries run at `now + 5s` (`reminders.py:261`). Discord logs in only after
  `set_webhook` (`main.py:160-163`).

Probes `p_failures.py` and P8:
```
P8 send before login raises: AttributeError '_MissingSentinel' object has no attribute 'is_set'
P5 reminder status after failed Discord send: failed | attempts: [('error', 'HTTPException', 'do_not_retry', None)]
```
This contradicts the review-queue line "Reminders just wait pending" and the runbook line "Telegram keeps working". The runbook
checklist item "After a restart, a missed Reminder's recovery summary arrives on the primary app" can fail for this reason alone.

**Fix (smallest):**
- Start Discord (login) **before** `initialize_runtime`.
- Build the registry only after a successful login, or give the registry an "available" predicate (adapter `is_ready()`) so that
  `for_user` returns None while the adapter is down. The Reminder then stays pending, matching the documented "down primary" model.
- Add the planned operator-visible signal.

### SF3. Shutdown and rolling deploys lose in-flight Discord Turns. `main.py:176-181`; `discord.py:183-188`
- discord.py runs each event as its own untracked task (`client.py:526`).
- `Client.close()` closes the websocket **and the HTTP session**, without waiting for those tasks (`client.py:801-815`).
- uvicorn drains in-flight HTTP requests (the Telegram webhook) before lifespan shutdown, but nothing drains Discord Turns.

During a rolling deploy both instances hold a gateway session and both receive the DM. If the old instance wins the claim:
- it runs the Turn, so the model call is made (and billed);
- its reply then fails on the closed HTTP session, or the task is cancelled when the loop ends;
- the claim stays `processing`, so the new instance treats any replay as a duplicate.

The result is "answered zero times". The runbook checks only "not twice".

`discord_channel.close()` also runs **before** `reminder_scheduler.shutdown()`, so a Reminder firing in that window fails as in
SF2. **Fix:**
- Track the `_dispatch` tasks in a set.
- In `close()`, stop the gateway first (`client.ws.close`), then `asyncio.wait(tasks, timeout=…)`, then close the client.
- Shut the scheduler down before closing Discord.
- Add "deploy during an in-flight Turn" to the spike checklist.

### SF4. A failed acknowledgement drops the button press. `update_claims.py:81-82`; `discord.py:150-152`
With `acknowledge_first`, an exception from `defer()` propagates before the claim:
- `NotFound` 10062 when the 3 s window passed (event-loop stall, cold start);
- 40060 "already acknowledged" (the other instance in a deploy overlap);
- a transient 5xx.

`_dispatch` then logs it as "Discord update failed". Probe:
```
P3 coordinator raised NotFound -> processed: [] claims: none
```
For 40060 during an overlap this is the *desired* dedup. For 10062 or a 5xx, a Done/Skip tap is silently not applied, and the
participant sees "interaction failed". **Decide and test:** either catch `discord.NotFound` / `HTTPException` in `acknowledge`
except 40060, log it, and continue (claims and the idempotency keys keep it single), or document the drop. There is no test of
the failure path today.

### SF5. Discord login can block Telegram startup. `main.py:160-166`
`await discord_channel.start()` runs `client.login()` inside lifespan startup. discord.py's HTTP layer:
- retries 5xx and `OSError` 5 times with `1 + tries*2` s sleeps (`http.py:646,767,781`);
- has no request timeout beyond aiohttp's default;
- with `max_ratelimit_timeout=None`, waits out any 429.

uvicorn serves nothing, the Telegram webhook included, until lifespan startup returns. This contradicts the comment "a bad token or
outage never stops Telegram" (true for a fast 401, not for an outage). **Fix:** `asyncio.wait_for(start(), 15)`, or move `login()`
into the background task. Also consider `Client(max_ratelimit_timeout=30)`, so a 429 can't hold a participant's Turn lock
indefinitely. That would be the library-level counterpart of the AGENTS.md "no aggressive retry loops" rule.

### SF6. Policy gate is "full access", but the policy says "owner/internal". `api/channels.py:36-48`; `handlers.py:236-242`; `pairing.py:30-42`
- The runbook and AGENTS.md say that before anyone who is not owner or internal uses Discord, the privacy promise and decision 04
  must be updated.
- The code admits, and the dashboard **actively offers "Connect Discord" to**, every account on `ALLOWED_TELEGRAM_CHAT_IDS`.
- AGENTS.md describes that list as "Full-access chats: all live Modes, no trial cap". It can therefore include non-internal
  participants.
- With CBT personal input enabled for full-access accounts, those participants could send CBT content through a processor not
  covered by decision 04.

**Fix:** the owner confirms that the full-access list is owner/internal only, or adds a separate owner list (for example
`DISCORD_ALLOWED_USER_IDS`) checked in the same three places.

## Nits

- **N1. The `open` posture skips the Discord full-access check** (`handlers.py:231-232` returns True before the non-Telegram
  branch). Production forbids `open` (`runtime_config.py:109`), but it is the default for local and dev setups. A linked account
  that has lost full access keeps using Discord there. Move the non-Telegram check above `open`, or document it.
- **N2. Revocation leaves proactive sends on Discord.** Remove a chat from the full-access list while Discord is its primary:
  - Reminders and nudges still go to Discord, because the proactive path has no access check;
  - the buttons are then refused with "Amigo isn't open to new users yet" (`handlers.py:153-159`), so Done and Later stop
    working.

  Fix: fall back to Telegram, or reset the primary to Telegram, when Discord access is lost.
- **N3. DM ordering.** Each gateway event is its own task, and the first await is the claim RPC. Network jitter can reorder two
  quick DMs before the Turn lock. Probe `p_order.py`: `processed order: ['actually make it 7', 'remind me at 6']`. Telegram has a
  similar exposure with concurrent webhooks. Consider a per-address FIFO before the claim, or accept and document it.
- **N4. `split_text`** (`discord.py:38-52`):
  - `max(rfind("\n\n"), rfind("\n"))` always picks the last `\n`, so the paragraph preference is dead code.
  - It splits inside code fences and strips leading indentation (`lstrip("\n ")`).
  - `split_text("") == [""]` sends an empty message, which Discord rejects.

  Probe: `fences per part [1, 1]`, `part2 start: 'code 162'` (indentation lost).
- **N5. Pairing copy.**
  - An expired or invalid code on Discord gets "can only be added to an activated Amigo account with full access…"
    (`pairing.py:56-66`) and logs "not a full-access account". Check the token's validity first.
  - `_INVALID_LINK` says "pairing link" on an app that uses a code.
  - The UI says the code "expires in a few minutes", but the TTL is 15 min (`memory/pairing.py:7`).
- **N6. `connect_link` doesn't validate `DISCORD_APPLICATION_ID`** (`discord.py:255-258`). A value with `&…` injects OAuth query
  parameters. It is owner config, so the risk is low; check `isdigit()`.
- **N7. Logging.**
  - At `LOG_LEVEL=DEBUG`, `discord.http` logs request bodies and responses (`http.py:660,707`), which include participant message
    content and user ids. `main.py:52-53` quiets only httpx and httpcore. Pin the `discord` logger at INFO or higher.
  - The token itself is never logged. Our logs use `type(error).__name__` only.
- **N8. Runbook accuracy** (`docs/runbooks/discord-dogfood.md`):
  - A short or placeholder `DISCORD_BOT_TOKEN` makes the **whole process refuse to start**: `runtime_config.py:83-86` runs at
    import in every environment. Only a well-formed but revoked token gives "gateway failed to start". Say so.
  - "The switch only appears while 2+ apps are linked, so switch back before disabling" is misleading. Disabling keeps the
    identity, so the switch stays visible. The real issue is SF2/SF3-style loss.
  - "A bot can DM someone only after they share a server" and the `scope=bot&permissions=0` install link are correctly marked
    to-verify. Keep both as spike checks.
  - Add the spike checks implied by SF1–SF5: a bad token, a deploy mid-Turn, a tap after a slow cold start.
- **N9. Test gaps.**
  - Nothing exercises the real `_build_client` or event registration (probe `p_discordpy.py` covers it and could become a test).
  - Untested: the lifespan start and failure branch, the `acknowledge` failure path, `edit_message_buttons` with non-empty buttons,
    and `MemoryStore.get_pairing_token_owner` (a Supabase query; needs a SQL-chain or staging check).
  - The `PrimaryChannel.jsx` connect flow has no web test runner (acknowledged in the review queue).
  - The plan's Phase 5 item "a tap on the old Telegram message resolves idempotently" isn't tested. By inspection it works:
    `telegram:reminder:…` and `discord:reminder:…` idempotency keys differ, and the second action hits `InvalidTransitionError`
    ("already resolved").

## Probes (scratchpad)
- `p_discordpy.py`: real Client, event wiring, ViewStore timeout, real interaction and DM dispatch (verifies the API).
- `p_failures.py`: SF1 (P2), SF4 (P3), SF2 (P5).
- `p_order.py`: N3.
- `p_modeflow.py`: Mode, Program and Memory flows on Discord with `threads=False`.
- Inline snippets: P7 (split), P8 (send before login), P9 (close never-started).
