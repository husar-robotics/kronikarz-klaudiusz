# Installing /ask-klaudiusz

Copy this directory into the `shrek-dog` repository at `.claude/skills/ask-klaudiusz/`, keeping `SKILL.md` and this file together.

Export the bot token in the shell that runs Claude Code sessions in `shrek-dog`:

```sh
export DISCORD_BOT_TOKEN=...
```

Verify the install by asking a session a question that should trigger the skill, for example "what did people say about actuator torque on Discord?" A working install runs a `search` through the `klaudiusz` CLI and answers with jump URLs.

If `DISCORD_BOT_TOKEN` is not set, any command that talks to Discord fails immediately with this message and exit code 1:

```
[FAIL] set DISCORD_BOT_TOKEN in the environment
```

Export the token and retry.
