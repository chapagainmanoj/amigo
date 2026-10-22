# One Telegram Topic per Mode

**Status: Accepted, pending spike.** Owner selected topics on 22 October 2026.
Implementation depends on the test-bot spike below; `/mode` remains the fallback.

Migration 016 assumes one Telegram chat per participant: a Session carries one `active_mode_id`, and moving between Modes is a confirmed switch inside the same chat history. Participants would rather see each Mode as its own conversation.

Telegram now supports topics in private chats with a bot. Bot API 9.3 (31 Dec 2025) added `User.has_topics_enabled`, `message_thread_id` / `is_topic_message` on incoming private messages, and `message_thread_id` on send methods. Bot API 9.4 (9 Feb 2026) let bots call `createForumTopic` in private chats and stop users creating or deleting topics (`User.allows_users_to_create_topics`). Topic mode is a per-bot setting in BotFather. The installed python-telegram-bot 22.8 speaks Bot API 10.0 and already exposes these fields.

We propose keeping one bot and giving each Mode its own topic inside the participant's private chat. The topic decides the Mode; there is no in-chat Mode switching.

## Considered Options

- **One chat, switch Modes (migration 016 as designed)** — Works today. Rejected as the primary design: every Mode shares one chat history, and isolation relies on Session boundaries the participant cannot see. Kept as the fallback if the spike fails.
- **One bot per Mode** — Each Mode gets its own chat, name and avatar. Rejected: a private `chat_id` equals the participant's Telegram id for every bot, which breaks the unique `user_profiles.telegram_chat_id`. It also needs one token and webhook per Mode, and pairing per bot.
- **Forum supergroup with topics** — Rejected: the participant would have to create a group and add the bot.
- **Topics in one private bot chat (chosen)** — One token, one pairing, `telegram_chat_id` stays unique. Telegram support is new, so it carries more risk.

## Consequences

- New migration: a `mode_topics` table, `(user_id, mode_id)` primary key, `(user_id, thread_id)` unique. It needs review, and `EXPECTED_SCHEMA_VERSION` must be bumped with it.
- `src/main.py` passes `message.message_thread_id` with `chat_id`. Messages with no thread, or an unknown thread, route to Daily.
- Active Sessions become per `(user_id, mode_id)`; `sessions.active_mode_id` becomes a fixed Mode set when the Session is created. The Store change is mirrored in `MemoryStore`, `InMemoryStore` and `FakeStore`.
- `MessageChannel.send_message` (plus edits and chat actions) gains an optional `thread_id`; all implementations are checked. If a topic send fails with "message thread not found", the message goes to the chat without a thread and the topic is recreated.
- Reminders always deliver to the Daily topic.
- The Daily topic is created when pairing succeeds; other Mode topics are created when their grant becomes active. User-created topics are turned off in BotFather.
- Handoffs still need confirmation. On confirmation, the new Task appears in the Daily topic.
- Pairing, the access gate, update deduplication and the dashboard are unchanged.
- Risk: on 8 May 2026, sends to private-chat topics failed with `message thread not found` and `createForumTopic` returned `BOT_FORUM_CREATE_FORBIDDEN` for most of a day ([tdlib/telegram-bot-api#847](https://github.com/tdlib/telegram-bot-api/issues/847), fixed the same day). The send fallback above covers this.

## Spike before accepting

On a throwaway test bot, without touching this codebase:

1. Turn on topic mode in BotFather; confirm `getMe` returns `has_topics_enabled: true`.
2. Call `createForumTopic` on a private chat; record the `message_thread_id`.
3. Send into the topic; reply from Telegram desktop, iOS and Android; confirm each update carries the thread id.
4. Send without a thread and note where it lands.
5. Delete the topic from the client and note what the next send to it returns.

## Open questions

- When a grant is revoked or expires, close the topic (read-only history) or delete it?
- What first message introduces each new topic?
- If a participant deletes a topic anyway, recreate it on their next message or at the next grant?
- Should the dashboard link to each topic?
