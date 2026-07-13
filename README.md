# Kronikarz Klaudiusz

Discord ↔ LLM bridge. Klaudiusz reads a Discord server's public channels over
the official bot REST API and writes back — the backend for two consumers: an
automatic **newsletter** and a **research log** built from repo + Discord
discussions. Cron-driven, zero always-on infrastructure.

Full design: [`docs/plans/2026-07-10-discord-llm-bridge.md`](docs/plans/2026-07-10-discord-llm-bridge.md)
(ingestion architecture) and
[`docs/plans/2026-07-12-consumers-design.md`](docs/plans/2026-07-12-consumers-design.md)
(the three consumers: `/ask-klaudiusz` skill, daily `#daily-tldr` newsletter,
research log).

## Tokens

Two bot identities exist ([design](docs/plans/2026-07-13-token-tiers.md)):

- **Klaudiusz** (writer) — can post the newsletter. Its token is held only by
  the maintainer and the scheduled routine, never shared.
- **Klaudiusz Reader** (read-only) — invited with View Channels + Read Message
  History only. Its token is what closed-beta users get, from the pinned
  message in the private beta channel. It is never committed to any repo.

Every command that talks to Discord resolves a token in this order, first hit
wins; write commands (`post-newsletter`) stop after the writer sources:

1. `DISCORD_BOT_TOKEN` in the environment (writer)
2. OS keychain `klaudiusz/discord-bot-token` (writer)
3. `DISCORD_READER_TOKEN` in the environment (reader)
4. OS keychain `klaudiusz/discord-reader-token` (reader)

Beta setup is one command — paste the reader token when prompted (input is
hidden, verified against Discord, then stored in your OS keychain):

```sh
uvx --from git+https://github.com/husar-robotics/kronikarz-klaudiusz klaudiusz auth
```

`klaudiusz whoami` shows which bot you are authenticated as and where the
token came from; `klaudiusz auth --clear` removes stored tokens. On a headless
box without an OS keychain, export `DISCORD_READER_TOKEN` instead.

Reader bot invite URL (View Channels + Read Message History, nothing else):
`https://discord.com/api/oauth2/authorize?client_id=<READER_APP_ID>&permissions=66560&scope=bot`

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
