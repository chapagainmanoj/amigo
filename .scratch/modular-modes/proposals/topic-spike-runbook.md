# Private-topic spike — owner execution required

Status: owner spike PASS on Desktop and iOS, 22 October 2026.
Android not tested (no device). No Telegram request executed by the builder.

Use a disposable test bot with private topic mode enabled in BotFather and no
configured webhook. Open its private chat first. The original probe requested Desktop, iOS and Android. Android was unavailable
in the accepted owner run; do not imply it was tested. The script consumes polling updates on this test bot and
creates a disposable topic; it never changes webhook configuration.

Set `TEST_BOT_TOKEN` in the process environment using your secret manager or a
hidden shell prompt; do not put its value in shell history or command arguments.

```sh
.venv/bin/python scripts/spike_private_topics.py \
  --test-bot --chat-id "$TEST_PRIVATE_CHAT_ID"
```

Supply a positive numeric private-chat ID. The token is read only from
`TEST_BOT_TOKEN` in the process environment; `--token` is no longer accepted.
The script never reads application Settings or `.env`. If the token equals
`TELEGRAM_BOT_TOKEN` in the process environment, it refuses before any request.
The owner must select the test token explicitly; unset production credentials
are not discoverable by this script.

The script checks `getMe.has_topics_enabled`, verifies there is no webhook,
verifies the private chat, creates a topic and sends into it. For each client,
reply in that topic with exactly the prompted marker, then press Enter in the
terminal. The script polls up to 60 seconds per client (adjust with `--polls`,
1–12 ten-second polls). It prints only update/thread IDs for matched replies;
unrelated messages and their content stay off console.

The original probe expected a thread-not-found rejection after deletion. The owner observed
that Telegram instead returns success and restores the topic. That expectation is superseded:
record restoration as observed behavior, not a failed acceptance gate. Never depend on deletion
producing an error, and never use an unthreaded resend as recovery. The historical script's
Android requirement/deletion verdict do not define the accepted design.

Return the console result plus these owner observations:

| Client | Version | Reply in topic | Thread ID matched | Notes |
|---|---|---|---|---|
| Desktop | | | | |
| iOS | | | | |
| Android | | | | |

## Accepted owner results — 22 October 2026

- `has_topics_enabled: true`; private `createForumTopic` worked.
- Desktop required updating/reopening before topic tabs appeared. A message from “New Chat”
  arrived in a newly created thread 225, distinct from created thread 223.
- Desktop and iOS rerun replies matched created thread 227. Client versions were not recorded.
  **Android not tested** (no device).
- Unthreaded send succeeded and created a new topic. All Phase 4 sends to a topics-enabled chat
  therefore require an explicit conversation, including pairing/errors/Reminders.
- Send to deleted thread 227 returned `ok:true` and restored it. Do not rely on “thread not found”.
- Disabling user-created threads in BotFather changed `allows_users_to_create_topics` to false
  and removed “New Chat”. Bot-created topic 235 still succeeded.
- Unverified: Android; where unthreaded sends land after user-created threads are disabled.

ADR 0003 **Accepted**. Phase 4 uses channel-neutral ConversationRef/capabilities and Mode state;
unknown conversations become additional Daily endpoints. Production may keep topic mode off and
use in-chat commands. If enabled, user-created threads must be off and every send explicitly addressed. Do not enable the production
bot's topic mode before reviewed Phase 4 deployment. Owner observations above are the evidence;
no tokens, private chat content or provider error bodies are retained here.

Deployment review now uses the full017–021 [schema21 cutover runbook](../../../docs/runbooks/mode-schema-21-cutover.md); no SQL has been applied by the builder.
