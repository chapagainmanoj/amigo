# ADR 0005: Declare the channel lifecycle in MessageChannel

## Status

Accepted. The owner approved it on 31 October 2026.

## Context

Two adapters now run in one process: Telegram, and Discord (ADR 0004). The `MessageChannel` interface has
grown parts that are real but undeclared:
- `ChannelRegistry` reads `getattr(channel, "ready", True)`.
- The dashboard reads `getattr(channel, "connect_link", None)`.
- `main.py` calls Telegram-only `initialize()`, and Discord-only `start()` and `close()`.

A caller can't learn these facts from the protocol. A new adapter that misses one fails silently: for example,
a channel that is never ready, or no install link.

## Decision

`MessageChannel` declares the lifecycle every adapter has:
- `ready: bool`: the adapter can deliver now. While it is False, proactive messages wait pending
  (`ChannelRegistry.for_user`).
- `async start() -> None`: connect or initialize, bounded by the caller. It may raise; callers decide
  whether that is fatal.
- `async close() -> None`: stop taking events, finish what is in flight (bounded), then disconnect.
- `connect_link: str | None`: where the dashboard sends a participant before Pairing this app, or None.

Implementations:
- Telegram: always `ready`, because Bot API sends need no connection. `start()` runs `initialize()`
  (capabilities and bot name). `main.py` keeps calling `initialize()` directly, because it needs the
  returned bot name, and webhook registration stays there. `close()` does nothing, because the webhook is
  deliberately left registered.
- Discord: `start()` and `close()` stay as they are.
- CLI, fakes and `SmokeChannel` (`scripts/smoke_check.py`): always ready, with no-op `start()` and
  `close()`.

Provider-specific ingress stays inside each adapter and outside the protocol: Telegram's `decode_update` and
`acknowledge_callback`, and Discord's gateway events.

## Consequences

- Six implementations change: TelegramChannel, DiscordChannel, CLIChannel, FakeChannel, SmokeChannel,
  and both FailingChannels through FakeChannel. AGENTS.md lists them.
- Callers use the attributes directly; the `getattr`/`hasattr` fallbacks go.
- `default_conversation_resolver` stays a Telegram-only hook. Only Telegram threads use it.
