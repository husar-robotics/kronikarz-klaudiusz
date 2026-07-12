# Design: the three consumers — /ask-klaudiusz, daily #daily-tldr newsletter, research log

**Date:** 2026-07-12
**Status:** proposed (design only, no implementation)
**Revised same day:** generation moved from the Messages API to a daily Claude Code routine, so it bills to the Max subscription instead of API pay-per-token (Marcin's constraint); see §2.
**Builds on:** [2026-07-10-discord-llm-bridge.md](2026-07-10-discord-llm-bridge.md). That plan settled the ingestion architecture: REST-only pulls, no gateway process, Message Content intent verified at G0, prompt-injection containment via `allowed_mentions` and withheld permissions. This document designs what runs on top of it.

## 1. What changed since the last plan

The 2026-07-10 plan sketched a weekly newsletter and a per-topic research log. The requirements are now:

1. **`/ask-klaudiusz`** — a skill in `shrek-dog` that pulls Discord discussions into a live Claude research session on demand.
2. **Daily newsletter** on `#daily-tldr`. Beyond a recap, it collects the papers and links people shared and adds learning material for the concepts that came up. The project is multi-discipline and educational; readers have very different backgrounds per field.
3. **Research log** — a day-by-day diary delivered as PRs to `docs/` in `shrek-dog`, fused from Discord and repo activity. Terse and context-friendly, with details split into subfolders. It serves LLM sessions directly and later feeds a public-facing rendering.

## 2. Decisions

### Stack: stay with Python

The package keeps `httpx`. The whole workload is API glue: pull JSON from Discord, prepare context for a generation session, post JSON back. No performance or concurrency demands exist that would justify a different runtime, and the G0 smoke test already works in this stack.

### Runtime and scheduler: a daily Claude Code routine on the Max subscription

Generation must draw on the Claude Max subscription rather than API pay-per-token billing (constraint added 2026-07-12). Subscription usage flows only through Claude products, so the raw Messages API is out. That inverts the control flow of the 2026-07-10 plan: a scheduled Claude Code session runs the scripts, instead of a script calling the model. Everything deterministic lives in `klaudiusz` CLI subcommands; the session contributes judgment only — picking topics, writing prose, deciding what counts as signal.

One **routine** (a Claude Code scheduled cloud task) runs daily at 06:30 Europe/Warsaw. It ingests the previous day once, then produces the newsletter and the research-log entry from that shared pull, so the two artifacts always describe the same window. Its cloud environment is attached to this repo and provides the three things the jobs need: environment secrets (`DISCORD_BOT_TOKEN`, `SHREK_DOG_TOKEN`), a cached setup script that installs the package, and **full network egress**. An allowlist was considered and rejected: `post-newsletter` HEAD-validates member-shared and web-search links on arbitrary domains, and an allowlist would 403 them all, making the validator drop live links wholesale. Containment rests on the existing measures (content treated as data, no mention permissions, human gates), not on egress filtering. The routine's configured instruction is one fixed line: follow `prompts/routine-daily.md` in this repo. The real prompt therefore stays versioned and reviewable in git.

Billing facts (verified 2026-07-12): routines consume the Max weekly usage limits, shared with interactive Claude Code use, and each account additionally has a daily allowance of routine runs. One run per day fits both comfortably.

Rejected alternatives:

- **Messages API on an API key.** The 2026-07-10 default. Rejected by the subscription constraint.
- **GitHub Actions with a `claude setup-token` OAuth token.** Subscription-billed and officially supported, and the fallback if routines prove limiting. Not the default because tokens minted for CI currently expire after about a day in practice despite a documented one-year lifetime ([claude-code-action#727](https://github.com/anthropics/claude-code-action/issues/727)), which an unattended daily job cannot tolerate.
- **Synology NAS.** A container on the NAS adds a machine to patch, monitor, and keep awake, and nothing in this design needs a standing process. It also shares the OAuth-token-expiry problem above. The NAS becomes the right home only if a future phase adds an interactive gateway bot that answers mentions in real time (noted in §7).

### Storage: stateless windows, artifacts in git

Each run computes its window from snowflake timestamps and pulls fresh. There is no database and no state file. Newsletters are archived in this repo under `newsletters/`; research-log entries live in `shrek-dog` under `docs/research-log/`. Raw JSONL pulls stay in the run's sandbox and vanish with it; they are never committed.

### Configuration: committed `config.toml`, secrets in env

The guild id and channel ids are not in the repo today; this file is where they land.

```toml
[discord]
guild_id = "..."
newsletter_channel_id = "..."   # starts as a staging channel, flipped to #daily-tldr at gate G3
ignore_channels = ["bot-news"]  # channels excluded from ingestion

[shrek_dog]
repo = "husar-robotics/shrek-dog"
log_dir = "docs/research-log"

[schedule]
timezone = "Europe/Warsaw"
quiet_day_message_threshold = 10
```

Secrets: `DISCORD_BOT_TOKEN` and `SHREK_DOG_TOKEN` live in the routine's cloud environment. `SHREK_DOG_TOKEN` is a fine-grained PAT scoped to `shrek-dog` with contents and pull-requests write, because nothing in the environment can otherwise open PRs in a second repo. No `ANTHROPIC_API_KEY` exists anywhere in this design.

## 3. Shared foundation (Phase 1)

The package grows from the ingestion module already planned. Layout:

```
klaudiusz/
  discord_api.py   # REST client: channels, threads (active + archived), messages,
                   # guild search, posting embeds; rate-limit header handling
  ingest.py        # windowed pull -> normalized records + a markdown transcript for prompts
  repo_signal.py   # gh CLI: commits, merged PRs, opened issues in shrek-dog for the window
  links.py         # URL extraction; arXiv/DOI metadata resolution; HEAD-request validation
  render.py        # chunk markdown into Discord messages/embeds within the 2000/4096/6000 limits
  cli.py           # `klaudiusz` entrypoint
  config.py        # config.toml + env
prompts/
  routine-daily.md # the routine's instructions: pipeline order, guardrails
  newsletter.md    # generation guidance for the newsletter
  research-log.md  # generation guidance for the log entry
```

The CLI is the contract every consumer shares:

```
klaudiusz channels                          # list readable channels
klaudiusz pull --channel <name|id> --since 3d [--json]
klaudiusz search "<query>" [--limit 25]     # guild message search
klaudiusz thread <id>
klaudiusz context --date 2026-07-11         # generation input: day transcript + repo signal + resolved link metadata
klaudiusz post-newsletter <file.md> --date 2026-07-11   # validate links, chunk to embeds, post, archive
klaudiusz publish-log <dir> --date 2026-07-11           # copy entry + details into a shrek-dog clone, open the PR
```

`pull` and `search` print a compact markdown transcript: author, channel, timestamp, content, jump URL. Every message keeps its jump URL so any downstream artifact can cite the source. The routine session sits between `context` and the two publish commands; everything on either side is deterministic and testable locally without a model. `context` exits with a distinct status on a quiet day (fewer than `quiet_day_message_threshold` messages and no repo activity), which tells the session to stop before generating anything.

## 4. Consumer 1: `/ask-klaudiusz` skill in shrek-dog

The capability ships as a skill wrapping the `klaudiusz` CLI. An MCP server was rejected for the default path: the skill loads only when invoked, adds nothing to standing session context, and needs no server configuration. The `barryyip0625/mcp-discord` option from the previous plan remains a documented alternative for people who prefer it.

**Mechanism.** `.claude/skills/ask-klaudiusz/SKILL.md` in `shrek-dog` instructs the session to run the CLI from this repo:

```sh
uvx --from git+https://github.com/husar-robotics/kronikarz-klaudiusz klaudiusz search "actuator torque"
```

`uvx` resolves and caches the package on first use, so `shrek-dog` takes no Python dependency. The session needs `DISCORD_BOT_TOKEN` in its environment; the skill states this and fails with a clear message when the token is absent.

**Skill contract.** Given a question about project discussions, the session:

1. runs `search` with 1–3 query variants, and `pull` on the channels or threads the hits point to,
2. synthesizes an answer in the session, quoting sparingly and citing jump URLs,
3. treats all Discord content as data. Instructions found inside messages are never followed. This is the prompt-injection surface of the whole design: untrusted server members write text that lands inside a coding session. The skill says so explicitly, and the residual risk is accepted because the same person reviews what the session does.

**Out of scope for the skill:** writing to Discord. It is read-only by instruction, and nothing in the CLI's `search`/`pull`/`thread` subcommands can post.

## 5. Consumer 2: daily newsletter on #daily-tldr

**Cadence.** The daily routine covers the previous local day. On a quiet day `context` says so and the session exits without posting.

**Generation.** The routine session writes the newsletter from the `context` output, following `prompts/newsletter.md`. The output has four sections:

1. **TL;DR** — three to six bullets for the whole server.
2. **Discussions** — one short digest per topic, each ending with jump URLs to the thread.
3. **Papers & links** — every paper and substantive link shared that day. Code, not the model, resolves arXiv/DOI metadata (title, authors) via the arXiv export API, and passes it into the context bundle, so titles are never hallucinated. Each item gets one line on why it came up.
4. **Learning corner** — the concepts a non-specialist would have to look up, each with a two-to-three-sentence plain explanation and one pointer to learn more. This section is the educational core: the model is told the audience spans disciplines and to pick concepts accordingly.

The session uses Claude Code's built-in web search so learning pointers can be real, current resources rather than recalled ones. `post-newsletter` then validates every outbound URL with a HEAD request; a dead link is dropped, and its entry falls back to plain text.

**Posting.** One lead message with the TL;DR, then the remaining sections as embeds in a thread under it, chunked by `render.py` to Discord's limits. `allowed_mentions: {parse: []}` on every message, as established at G0. `post-newsletter` writes `newsletters/YYYY-MM-DD.md` and the routine commits it to this repo, so the archive outlives Discord scrollback.

**Trust ramp.** `newsletter_channel_id` starts pointed at a staging channel. After about a week of issues that read accurately against the server, Marcin flips the config value to `#daily-tldr` (gate G3). This replaces the PR-review mode from the weekly design, which is too heavy for a daily cadence.

## 6. Consumer 3: research log in shrek-dog

**Shape in the repo.** The log keeps terse entries in monthly files, splits longer material into a details folder, and has a hand-written index:

```
docs/research-log/
  README.md                     # what this log is, how to read it, entry taxonomy
  2026-07.md                    # one dated section per day
  details/
    2026-07-12-mjx-divergence.md
```

A day's entry is at most ~6 bullets, each tagged and linked:

```markdown
## 2026-07-12
- **Decision:** leg actuators switch to QDD after the torque-density comparison
  ([discussion](https://discord.com/channels/...), [PR #42](...))
- **Result:** MJX run converged after the contact-parameter fix; 1.8 m/s on flat terrain
  ([details](details/2026-07-12-mjx-divergence.md))
- **Question:** sim2real friction gap unresolved; two calibration approaches proposed
  ([thread](https://discord.com/channels/...))
```

Monthly files keep any single file small enough to drop into an LLM context whole. A details file is written only when a topic produced enough substance (an experiment write-up, a paper discussion, a design argument) that compressing it to one bullet loses information a future session would need.

**Generation.** The same routine run continues to the log after the newsletter, on the same `context` output. The prompt receives the current month's file and the previous 14 days of entries, and is instructed to report only what changed: an ongoing topic reappears only when a decision lands, a result arrives, or the direction moves. Banter, logistics, and restatements of known state are filtered by an explicit taxonomy in the prompt (Decision / Result / Direction / Question / Resource). A day with nothing that qualifies produces no entry and no PR.

The session writes the entry and any details files into an output directory; `publish-log` checks paths and formats before anything leaves the sandbox.

**Delivery.** `publish-log` clones `shrek-dog`, writes to branch `research-log/YYYY-MM-DD`, and opens a PR with `SHREK_DOG_TOKEN`. Marcin merging the PR is the human gate on everything that enters `shrek-dog` history. If daily PRs prove noisy, batching to a weekly PR is a config change, not a redesign.

**Public-facing rendering is deferred.** The log and details files are written as the source of truth; a later phase adds a generator that renders reader-friendly posts from them. Nothing in this phase is written for public consumption, which keeps the prompts honest about their one audience: project members and LLM sessions.

## 7. Phases and gates

Numbering continues the 2026-07-10 plan; its Phase 0 is done.

| Phase | Deliverable | Gate |
|---|---|---|
| 1 | Ingestion + CLI (`channels`, `pull`, `search`, `thread`), config.toml, link/metadata module | Full-server pull matches a manual spot-check of 3 channels + 1 forum thread; `uvx` run works from outside the repo |
| 2 | `/ask-klaudiusz` skill (PR to `shrek-dog`) | **G2:** Marcin uses it in a real session; answers check out against Discord |
| 3 | Daily routine (cloud environment with secrets + setup script, `prompts/routine-daily.md`) posting the newsletter to a staging channel | **G3:** ~a week of accurate issues; Marcin flips the channel id to `#daily-tldr` |
| 4 | Log step added to the routine; research-log PRs to `shrek-dog` | **G4:** three consecutive daily PRs merged without substantive corrections |
| 5 (later) | Public-facing rendering of the log; optionally an interactive @Klaudiusz responder (gateway process; the NAS becomes relevant here) | — |

The skill ships before the automated consumers on purpose: daily interactive use of `search`/`pull` shakes out ingestion bugs while a human is looking at the output, before the unattended routine depends on the same code.

## 8. Risks

| Risk | Handling |
|---|---|
| Hallucinated paper titles or learning links | Paper metadata resolved by code from arXiv/DOI; web-search-grounded learning links; HEAD validation drops dead URLs before posting |
| Prompt injection: Discord text inside a coding session (skill) or inside generated artifacts | Skill tells the session to treat Discord content as data and never follow instructions found in it; bot cannot mention anyone; log enters `shrek-dog` only through a human-reviewed PR |
| Daily research-log PRs become noise in `shrek-dog` | No-signal days produce no PR; weekly batching is a config flag |
| Re-reporting ongoing topics as news | Generator sees the previous 14 days of entries and reports deltas only |
| `SHREK_DOG_TOKEN` leak | Fine-grained PAT limited to one repo, contents + pull-requests only |
| A heavy interactive week exhausts the shared Max limit | The jobs skip until the weekly reset; enabling usage credits (metered overage) is the opt-in escape hatch |
| The routine session drifts from the pipeline (improvises instead of following it) | All plumbing is CLI subcommands; the prompt is fixed and versioned in git; `post-newsletter` and `publish-log` validate their input before any side effect |
| Routine runs late or is retried | The window is computed from dates, not run time, so a late or repeated run produces the same content |
| Quiet days waste a run | `context` detects the quiet day and the session exits before generating |

## 9. Cost envelope

Generation bills to the Max subscription's weekly limits. Two small generations a day (roughly 10–50k input tokens of context each) are a negligible slice of a Max plan, and the per-account daily allowance of routine runs covers one run per day with room to spare. Discord and arXiv APIs are free. No API key and no per-token spend exist anywhere in the design; the marginal cash cost on top of the existing subscription is zero.
