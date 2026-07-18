# Kronikarz Klaudiusz

Discord ↔ LLM bridge for the husar-robotics community. Klaudiusz reads the
project's Discord server over the official bot REST API and writes back — the
backend for three consumers: an `/ask-klaudiusz` skill for Claude Code
sessions, an automatic daily **newsletter**, and a **research log** built from
repo + Discord discussions. Cron-driven, zero always-on infrastructure.

The tool is purpose-built for one guild (its id is baked into `config.toml`)
and every command needs a bot token for that guild — so while the code is
public, running it is useful to community members only.

## Quick start (community beta)

Run the CLI through `uvx` — no install, no clone:

```sh
uvx --from git+https://github.com/husar-robotics/kronikarz-klaudiusz klaudiusz --help
```

Set the read-only bot token in your environment. It comes from the pinned
message in the private beta channel on Discord — export it in the shell (or
shell profile) that runs your sessions, and never commit it anywhere:

```sh
export DISCORD_READER_TOKEN=...
uvx --from git+https://github.com/husar-robotics/kronikarz-klaudiusz klaudiusz whoami
```

Read commands:

| command | what it does |
| --- | --- |
| `channels` | list the guild's text, announcement, and forum channels |
| `search <query> [--limit N]` | search the guild's message history |
| `pull --channel <name\|id> --since <Nd\|YYYY-MM-DD> [--json]` | one channel's messages and threads |
| `thread <id>` | full transcript of one thread |
| `context --date YYYY-MM-DD [--out DIR]` | assemble a day's context bundle |
| `whoami` | which bot token the commands would use, and whose it is |

`post-newsletter` and `publish-log` are operator commands: they run inside the
scheduled routine and need the writer token / a shrek-dog PAT.

## Tokens

Two bot identities exist ([design](docs/plans/2026-07-13-token-tiers.md)):

- **the writer** ("Klaudiusz") — can post the newsletter. Its token is held
  only by the maintainer and the scheduled routine, never shared.
- **the reader** — invited with View Channels + Read Message History only.
  Its token is what beta users get from the pinned beta-channel message. It is
  never committed to any repo.

Every command resolves a token from the environment, first hit wins; write
commands stop after the writer source:

1. `DISCORD_BOT_TOKEN` (writer)
2. `DISCORD_READER_TOKEN` (reader)

In a development checkout the CLI folds the gitignored repo-root `.env` into
the environment at startup (real environment variables always win), so tokens
live there once and never need manual sourcing. The routine's cloud
environment sets them directly.

## Development

```sh
uv sync
uv run pytest
uv run ruff check .
```

Python 3.11–3.12, `httpx` + `python-dotenv` as the only runtime dependencies.
Design docs live in [`docs/plans/`](docs/plans/) — start with the
[ingestion architecture](docs/plans/2026-07-10-discord-llm-bridge.md) and the
[three consumers](docs/plans/2026-07-12-consumers-design.md).

## Maintainer: bot setup

- **Reader bot** — one-time Developer Portal checklist (Message Content intent
  ON, Public Bot OFF, invite with `permissions=66560`) in the
  [token-tiers design doc](docs/plans/2026-07-13-token-tiers.md).
- **Writer bot** — same portal steps but invited with
  `permissions=84992` (adds Send Messages + Embed Links; never Mention
  Everyone), then verified with the Phase 0 smoke test:

  ```sh
  DISCORD_BOT_TOKEN=... uv run smoke.py <guild_id> <channel_id>
  ```

  The script passes (gate G0) when it authenticates, reads a human-authored
  message with non-empty content (proving the Message Content intent is ON),
  and posts a test message. Guild and channel ids come from Discord's
  Developer Mode (right-click → Copy ID / Kopiuj identyfikator).

## License

[MIT](LICENSE)
