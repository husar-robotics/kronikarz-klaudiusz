# Kronikarz Klaudiusz

Discord ↔ LLM bridge. Klaudiusz reads a Discord server's public channels over
the official bot REST API and writes back — the backend for two consumers: an
automatic **newsletter** and a **research log** built from repo + Discord
discussions. Cron-driven, zero always-on infrastructure.

Full design: [`docs/plans/2026-07-10-discord-llm-bridge.md`](docs/plans/2026-07-10-discord-llm-bridge.md).

## Phase 0 — smoke test (gate G0)

Prerequisites (manual, Discord Developer Portal):

1. Enable **Message Content Intent** (Bot tab). Without it, message `content`
   reads back empty over REST and gateway alike — the whole pipeline goes blank.
2. Invite the bot with **View Channels, Read Message History, Send Messages,
   Embed Links**. Do *not* grant Mention Everyone. Invite URL, built from the
   app's own client id:
   `https://discord.com/api/oauth2/authorize?client_id=<APP_ID>&permissions=84992&scope=bot`
3. Turn on Developer Mode in Discord and copy the **guild (serwer) ID** and the
   target **channel ID** (right-click → Kopiuj identyfikator).

Then, with a normal human message present in the channel:

```sh
DISCORD_BOT_TOKEN=... uv run smoke.py <guild_id> <channel_id>
```

G0 passes when the script authenticates, reports the intent **ON** (by reading a
human-authored message with non-empty content), and posts a test message. If it
reports the intent OFF or inconclusive, it tells you exactly what to fix.
