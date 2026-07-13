# Installing /ask-klaudiusz

Copy this directory into the `shrek-dog` repository at `.claude/skills/ask-klaudiusz/`, keeping `SKILL.md` and this file together.

Store the read-only bot token once in the OS keychain. The token comes from the pinned message in the private beta channel on Discord; the prompt hides your input, verifies the token against Discord, and never echoes it:

```sh
uvx --from git+https://github.com/husar-robotics/kronikarz-klaudiusz klaudiusz auth
```

On a headless machine without an OS keychain (no macOS Keychain, no Secret Service), export the token in the shell that runs Claude Code sessions instead:

```sh
export DISCORD_READER_TOKEN=...
```

Verify the install with `klaudiusz whoami` (it should report the reader bot), then ask a session a question that should trigger the skill, for example "what did people say about actuator torque on Discord?" A working install runs a `search` through the `klaudiusz` CLI and answers with jump URLs.

If no token is available, any command that talks to Discord fails immediately with this message and exit code 1:

```
[FAIL] no Discord token found; run 'klaudiusz auth' to store the reader token, or set DISCORD_BOT_TOKEN / DISCORD_READER_TOKEN in the environment
```

Run `klaudiusz auth` and retry.
