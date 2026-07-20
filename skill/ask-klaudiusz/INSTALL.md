# Installing /ask-klaudiusz

Copy this directory into the `shrek-dog` repository at `.claude/skills/ask-klaudiusz/`, keeping `SKILL.md` and this file together.

Export the read-only bot token in the shell (or shell profile) that runs Claude Code sessions. The token comes from the pinned message in the private beta channel on Discord — never commit it or paste it into a chat:

```sh
export DISCORD_READER_TOKEN=...
```

Verify the install with `klaudiusz whoami` (it should report the reader bot), then ask a session a question that should trigger the skill, for example "what did people say about actuator torque on Discord?" A working install runs a `search` through the `klaudiusz` CLI and answers with jump URLs.

If no token is available, any command that talks to Discord fails immediately with this message and exit code 1:

```
[FAIL] no Discord token found; set DISCORD_BOT_TOKEN or DISCORD_READER_TOKEN in the environment or the repo-root .env
```

Export `DISCORD_READER_TOKEN` and retry.
