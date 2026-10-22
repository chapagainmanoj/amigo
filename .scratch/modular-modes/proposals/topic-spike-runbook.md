# Private-topic spike — owner execution required

Status: prepared; no Telegram request executed by the builder.

Use a disposable test bot with private topic mode enabled in BotFather and no
configured webhook. Open its private chat first. Have Telegram desktop, iOS and
Android available. The script consumes polling updates on this test bot and
creates a disposable topic; it never changes webhook configuration.

```sh
.venv/bin/python scripts/spike_private_topics.py \
  --test-bot --token "$TEST_BOT_TOKEN" --chat-id "$TEST_PRIVATE_CHAT_ID"
```

Supply a positive numeric private-chat ID. The token is an explicit argument;
the script never reads application Settings or `.env`. If the token equals
`TELEGRAM_BOT_TOKEN` in the process environment, it refuses before any request.
The owner must select the test token explicitly; unset production credentials
are not discoverable by this script.

The script checks `getMe.has_topics_enabled`, verifies there is no webhook,
verifies the private chat, creates a topic and sends into it. For each client,
reply in that topic with exactly the prompted marker, then press Enter in the
terminal. The script polls up to 60 seconds per client (adjust with `--polls`,
1–12 ten-second polls). It prints only update/thread IDs for matched replies;
unrelated messages and their content stay off console.

After all three clients, inspect where the message sent without a thread ID
appears. Delete the created topic, then press Enter. The final send must return
a thread-not-found rejection. Other API errors or a successful send fail the
spike. The script does not retry the send outside the deleted topic.

Return the console result plus these owner observations:

| Client | Version | Reply in topic | Thread ID matched | Notes |
|---|---|---|---|---|
| Desktop | | | | |
| iOS | | | | |
| Android | | | | |

Also record the unthreaded message's location and deletion behavior. Never
paste tokens, chat content or provider errors. ADR 0003 stays **Accepted,
pending spike** until the owner reports results. Phase 4 depends on this result.
