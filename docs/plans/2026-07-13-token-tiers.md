# Two-tier Discord tokens: reader bot + OS-keychain storage

Date: 2026-07-13. Status: accepted, implemented on `feat/token-tiers`.

## Problem

Closed-beta users need the read commands (`channels`, `pull`, `search`,
`thread`, `context`) — the `/ask-klaudiusz` skill runs them — but the only
credential was `DISCORD_BOT_TOKEN`, the writer bot's token. Sharing it would
hand every beta user the ability to post as Klaudiusz, and `export`-based
setup leaves the token in shell history and dotfiles.

## Design

**Two bot identities.** Discord ACLs attach to the bot user, not the token, so
genuinely read-only access requires a second application: **Klaudiusz Reader**,
invited with View Channels + Read Message History only (permissions `66560`).
A leaked reader token can read what every guild member already sees — nothing
more. The writer token never leaves the maintainer and the scheduled routine.

**Capability by presence, not probing.** Which tier a command runs at is fully
determined by which token resolves — no runtime permission checks. Resolution
order, first hit wins:

1. `DISCORD_BOT_TOKEN` env → writer
2. OS keychain `klaudiusz/discord-bot-token` → writer
3. `DISCORD_READER_TOKEN` env → reader
4. OS keychain `klaudiusz/discord-reader-token` → reader

Write commands (`post-newsletter`) stop after step 2 and fail with a message
naming `klaudiusz auth --writer`, before any client is constructed or network
request fires. Read commands accept either tier.

**Keychain storage.** `klaudiusz auth` prompts via `getpass` (input hidden,
never in argv or shell history), verifies the token against
`GET /users/@me` (a 401 stores nothing), and writes it to the OS keychain via
the `keyring` library — macOS Keychain, Windows Credential Manager, or Secret
Service on Linux. `klaudiusz whoami` reports the resolved bot, tier, and
source; `klaudiusz auth --clear` deletes both entries. On headless boxes
without a keychain backend, *reading* degrades silently to env-only (the
routine and CI keep working), while *storing* fails loudly so `auth` never
pretends to have saved something.

This supersedes the "secrets come only from the environment" rule in
`2026-07-12-implementation-plan.md`; env vars remain supported and always win.

## Distribution and rotation

The reader token lives in a **pinned message in the private beta channel**.
That channel's ACL is exactly the set of people the token is for — leaking it
to a guild member grants nothing they don't have. It is never committed:
Discord partners with GitHub secret scanning and auto-revokes tokens pushed to
public repos, and repo clones outlive guild membership.

Rotation (e.g. when someone leaves the beta): regenerate the token in the
Developer Portal, edit the pinned message, announce; users rerun
`klaudiusz auth`. The old token dies server-side immediately; a stale keychain
shows up in `klaudiusz whoami` as a 401 naming its source.

Out of scope: `SHREK_DOG_TOKEN` stays env-only — `publish-log` is
routine/operator territory and beta users never run it.

## Manual setup checklist (Developer Portal, one-time)

1. Create the application **Klaudiusz Reader**; on the Bot tab set
   **Message Content Intent ON** (without it, message `content` reads back
   empty — the Phase 0 failure mode) and **Public Bot OFF**; copy the token.
2. Invite it with
   `https://discord.com/oauth2/authorize?client_id=1526141917933473792&permissions=66560&scope=bot`
   — View Channels + Read Message History, no Send Messages. Make sure it can
   only see channels all members can see, or the shared token over-grants.
3. Verify: `klaudiusz auth` (paste the token → `[OK] verified as Klaudiusz
   Reader…`), `klaudiusz whoami` (tier reader, source keychain),
   `klaudiusz channels`. Then confirm the gate: `klaudiusz post-newsletter …`
   without a writer token must fail naming `auth --writer`.
4. Pin the token in the private beta channel, with the rotation note next to
   it.
