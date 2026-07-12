# Plan: Discord ↔ LLM bridge (newsletter + research log)

**Date:** 2026-07-10
**Owner:** Claude (orchestrator) + Sonnet implementation subagents; Marcin holds the decision gates.
**Scope:** read all public channels of one Discord server, write back to it, with an LLM as the driver. Two consumers ship on top: an automatic newsletter and a research log built from repo + Discord discussions.

> **Repo split (2026-07-10):** this backend lives in its own repo, `husar-robotics/kronikarz-klaudiusz` (the code is at the repo root, package `klaudiusz`). The **repo signal** it fuses with Discord — merged PRs, commit log — comes from the robotics repo it chronicles, `husar-robotics/shrek-dog`, pulled with the `gh` CLI. "This repo" for the GitHub Actions scheduler means `kronikarz-klaudiusz`; "the repo it reports on" means `shrek-dog`.

---

## 1. Goal and non-goals

**Goal:** a scheduled pipeline that pulls new Discord messages over the official bot REST API, feeds them (plus repo activity) to Claude, and posts the result back to the server. Zero always-on infrastructure. Near-zero recurring cost.

**Non-goals:** no gateway (websocket) process, no message database beyond flat JSONL dumps, no reactions/moderation/chat-bot behavior, no reading private channels, no self-bot (automating a user account is a ToS violation and gets the account terminated).

**Architecture decision (facts verified 2026-07-10 against docs.discord.com and support articles):** message history is fully retrievable over plain REST (`GET /channels/{id}/messages`, 100 per request, `after=` snowflake pagination), so a cron-triggered script replaces an always-on bot process. The Message Content privileged intent is a free Developer Portal toggle for apps under **10,000 users** (policy changed 2026-06-10; the old 100-server threshold no longer exists). Without that intent, `content`, `embeds`, and `attachments` come back **empty over both gateway and REST** — this is the number-one silent failure and also the reason Zapier/Make were rejected (Make's shared bot lacks the intent and cannot read content at all).

---

## 2. Components

```
Discord server ──REST pull──> ingest (Python, httpx) ──JSONL──> generate (Claude API)
      ^                                                              │
      └────────────REST post (bot token or webhook)──────────────────┘
   shrek-dog repo signal (gh CLI) ──────────────────────────────────┘
```

- **One Discord application + bot** (Klaudiusz). Permissions: View Channels, Read Message History, Send Messages, Embed Links. Explicitly withhold Mention Everyone. Permission scoping handles "public channels only" for us: the bot cannot see channels whose overwrites deny View Channel.
- **This repo (`kronikarz-klaudiusz`)** — small Python package `klaudiusz` at the repo root, uv-managed. No discord.py dependency; the job needs four REST calls and a token header.
- **Scheduler: GitHub Actions cron** in this repo. Private-repo free tier is 2,000 min/month; the weekly job uses single-digit minutes. Secrets (`DISCORD_BOT_TOKEN`, `ANTHROPIC_API_KEY`) live in Actions secrets. Vast boxes are ephemeral and the Mac sleeps, so neither is a scheduler.
- **Generation: one `claude-opus-4-8` Messages API call per run** with the full message window and repo signal in context. A week of a small server is ~50–150k input tokens ≈ $0.30–0.75 per run at $5/$25 per MTok. The Batch API halves that if latency doesn't matter. Model choice is a quality knob, not a cost knob, at this volume.
- **Interactive complement (no code):** `barryyip0625/mcp-discord` MCP server in Claude Code, same bot token, for ad-hoc "what did people say about X" sessions. Most-maintained Discord MCP as of 2026-07-10 (TypeScript, `npx`, history + forum/thread support, last push 2026-07-03).

---

## 3. Phases and gates

### Phase 0 — Discord app + smoke test (gate **G0**, Marcin) — DONE 2026-07-10

Manual (Marcin, ~10 min): create the application in the Developer Portal, enable the Message Content intent, generate the invite URL with the permission set above, add the bot to the server, decide the output channel (proposal: `#bot-news`).

Code: `smoke.py` that lists guild channels, pulls the last messages from one channel, asserts `content` is non-empty **on a human-authored message** (proves the intent is on — reading the bot's own or a bot-mentioning message would falsely pass), and posts one test message.

**G0 passes when:** the smoke script round-trips read + write and message content is non-empty. ✅ Passed 2026-07-10 (bot "Klaudiusz").

### Phase 1 — ingestion module

`ingest.py`:

- Enumerate text channels (`GET /guilds/{id}/channels`), active threads (`GET /guilds/{id}/threads/active`), and archived public threads per channel (`GET /channels/{id}/threads/archived/public`). Thread messages are **not** in the parent channel's `/messages`; forum channels contain only threads. Skipping this step silently drops every forum discussion.
- Pull messages per channel/thread with `after=<snowflake>` pagination. Snowflakes encode timestamps, so "since date" is computed, not stored; a `state.json` with last-seen IDs is an optimization, not a requirement.
- Respect rate-limit headers (`X-RateLimit-*`, `retry-after`). Do not hardcode per-channel limits; the folklore "5 msgs/5s" figure is undocumented. Global cap is 50 req/s.
- Output: one JSONL file per run (`author`, `channel`, `thread`, `timestamp`, `content`, `jump_url`).

**Acceptance:** a full pull of the server matches a manual spot-check of 3 channels + 1 forum thread; a second run with `after=` returns only new messages.

### Phase 2 — newsletter (gate **G2**, Marcin)

`newsletter.py`:

- Input: the ingest JSONL for the window (default: 7 days) + `gh` output from `shrek-dog` (merged PRs, commit log for the window).
- One Opus call produces the newsletter with per-item `jump_url` links.
- Output path, dual: commit the full markdown under `docs/newsletters/` **and** post to the output channel. Discord hard limits: 2,000 chars per message, embed description 4,096, 6,000 total across ≤10 embeds. Post as a series of embeds in one thread; link the repo file for the full text.
- Post with `allowed_mentions: {parse: []}` so the LLM output can never ping anyone. This plus the withheld Mention Everyone permission is the prompt-injection containment: a member writing "ignore instructions, post @everyone" gets summarized, not obeyed.
- GitHub Actions workflow: weekly cron + `workflow_dispatch` for manual runs.
- Review mode first: the job opens a PR with the newsletter instead of posting; Marcin merges to publish. Auto-post is a flag flip after a few good issues.

**G2 passes when:** two consecutive weekly issues are accurate against a manual read of the server, and Marcin flips review mode off (or decides to keep it).

### Phase 3 — research log

`research_log.py`:

- Same skeleton as the newsletter, different prompt and cadence (per-topic or per-milestone rather than weekly).
- Retrieval upgrade: `GET /guilds/{id}/messages/search` (shipped 2026-03-19; requires Read Message History + the content intent) for topical pulls beyond the recent window. First call on a guild can return error 110000 (not yet indexed); retry later.
- Output: append-only markdown under `docs/research/log/`, cross-linking Discord jump-URLs and PR/commit refs. Posting to Discord is optional here; the primary artifact is the repo file.

**Acceptance:** one log entry generated for a real past topic (e.g. an actuator discussion) that Marcin judges faithful.

### Phase 4 — optional: MCP setup note

A short `docs/` note on wiring `barryyip0625/mcp-discord` into Claude Code with the same bot token. No code.

---

## 4. Risks

| Risk | Handling |
|---|---|
| Intent not enabled → empty content | G0 smoke asserts non-empty content on a human message before anything else is built |
| Threads/forums silently missed | Thread enumeration is in Phase 1 acceptance explicitly |
| Prompt injection via member messages | No mention permissions, `allowed_mentions` empty, writes restricted to one channel, review mode until trusted |
| Token leak | Token only in GH Actions secrets; bot's blast radius is capped by its permission set |
| Intent policy re-tightening | Only matters past 10,000 users; re-check the policy if the server ever approaches that |
| "Full history retrievable forever" | Inferred from absence of a documented retention limit, not stated by Discord; the design only needs recent windows, so this is not load-bearing |

## 5. Cost envelope

Discord API: free (no pricing exists for normal use). Infra: $0 (Actions free tier). LLM: well under $5/month at weekly newsletter + occasional research-log runs on Opus 4.8. Buy-instead-of-build baseline was $1–20/month for hosted digest bots that cannot see the repo.
