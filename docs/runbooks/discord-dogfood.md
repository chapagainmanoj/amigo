# Discord dogfood: the multi-app proof (owner only)

Discord runs as a second messaging app inside the web process (ADR 0004). It is off by default, and only accounts
on the full-access list (`ALLOWED_TELEGRAM_CHAT_IDS`) can use it (owner decision, 31 Oct 2026). Decision 16 still
says No Expansion Yet for production. While Discord is enabled, every full-access account is offered "Connect
Discord". Before enabling it, make sure that list holds only owner and internal accounts. Otherwise, first update
the privacy promise and decision 04, because Discord would become a processor of participant messages.

## 1. Create the bot (Discord Developer Portal)
1. Create a New Application, for example "Amigo (dogfood)". Copy the **Application ID**.
2. On the **Bot** page, reset the token and copy it. Leave the privileged intents **off**: DMs to the bot do not
   need Message Content.
3. Create a private server for yourself. You will add the bot there in step 3: a bot can DM someone only after
   they share a server. Confirm this in the spike.

## 2. Configure (owner edits `.env` or the Render environment; agents never do)
```
DISCORD_ENABLED=true
DISCORD_BOT_TOKEN=<token>
DISCORD_APPLICATION_ID=<application id>
```
Restart. The log says `Discord gateway connecting`.
- A token that is missing, shorter than 50 characters, or looks like a placeholder fails configuration validation,
  and the **whole app refuses to start**, Telegram included.
- A well-formed but wrong token logs `Discord gateway failed to start`, and Telegram keeps working.
- If the gateway stops later, the log says `Discord gateway stopped`.

Until Discord is connected, Reminders for participants whose primary app is Discord wait pending. They are not lost.

Hosting: the Render free plan sleeps when idle. The Discord gateway can't wake it, so DMs sent while it sleeps
are lost. For anything longer than a short spike, use an always-on instance (an owner cost decision).

## 3. Pair
1. Sign in to the dashboard with your full-access account. Under **Where Amigo reaches you**, choose
   **Connect Discord**.
2. Use **Add Amigo in Discord** to add the bot to your private server. Then DM the bot the `/pair <code>`
   shown on the dashboard. The code is single use and expires in a few minutes.
3. Refresh settings. Discord appears as linked, and the primary-channel choice appears.

## 4. Spike checklist (record results in `.scratch/modular-modes/review-queue.md`)
- [ ] A Discord DM gets a reply on Discord. Telegram still replies on Telegram.
- [ ] Typed `/mode` and `/help` arrive as plain text, not as a slash-command picker. If not, note it: we would
      register slash commands.
- [ ] `/mode` buttons switch Mode. A Reminder's Done/Later buttons work, with no "interaction failed" banner.
- [ ] With Discord as primary, a Reminder arrives on Discord only. Switch back, and the next one arrives on Telegram.
- [ ] A long reply (over 2000 characters) arrives in parts, in order.
- [ ] After a restart, a missed Reminder's recovery summary arrives on the primary app.
- [ ] Messages sent during a deploy are answered once, not twice (two gateway sessions may overlap).
- [ ] Optional: remove the bot from the server, and check whether a Reminder then fails visibly in logs.

## Turning it off
Set `DISCORD_ENABLED=false` and restart. Linked identities remain, and so does the dashboard switch, because 2 apps
are still linked. Participants whose primary app is Discord get no Reminders (they wait pending) until they switch
back to Telegram on the dashboard. Ask them to switch first.
