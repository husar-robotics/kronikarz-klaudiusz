#!/usr/bin/env python
"""Phase 0 smoke test (gate G0) for Kronikarz Klaudiusz.

Proves three things end to end before any real code is built:
  1. the bot token authenticates and can list the guild's channels,
  2. the Message Content intent is actually ON (the #1 silent failure),
  3. the bot can post back to the chosen channel.

The intent check is the subtle one. Discord always hands a bot the content of
messages it authored itself or that @-mention it, EVEN WITH THE INTENT OFF. So
reading back our own test message would pass regardless and prove nothing. The
only honest check is to read a message written by a human who did not mention
the bot: if such a message exists and its content is empty, the intent is off.

Run:
    DISCORD_BOT_TOKEN=... uv run smoke.py <guild_id> <channel_id>

<channel_id> is where the test message gets posted and read from. Make sure a
human has said something in that channel recently, otherwise the intent check
is inconclusive (the script says so rather than claiming success).
"""

from __future__ import annotations

import os
import sys

import httpx

API = "https://discord.com/api/v10"
UA = "DiscordBot (https://github.com/husar-robotics/kronikarz-klaudiusz, 0.1.0)"


def client(token: str) -> httpx.Client:
    return httpx.Client(
        base_url=API,
        headers={"Authorization": f"Bot {token}", "User-Agent": UA},
        timeout=30.0,
    )


def check(resp: httpx.Response) -> httpx.Response:
    """Fail loudly with Discord's error body, which is far more useful than a bare status."""
    if resp.is_error:
        sys.exit(f"[FAIL] {resp.request.method} {resp.request.url} -> {resp.status_code}\n{resp.text}")
    return resp


def list_channels(c: httpx.Client, guild_id: str) -> list[dict]:
    chans = check(c.get(f"/guilds/{guild_id}/channels")).json()
    text_like = [ch for ch in chans if ch.get("type") in (0, 5)]  # 0 = text, 5 = announcement
    print(f"[ok]  guild {guild_id}: {len(chans)} channels, {len(text_like)} text/announcement")
    for ch in text_like[:15]:
        print(f"        #{ch['name']}  (id {ch['id']})")
    return chans


def check_intent(c: httpx.Client, channel_id: str, bot_id: str) -> None:
    msgs = check(c.get(f"/channels/{channel_id}/messages", params={"limit": 50})).json()
    # A message that truly tests the intent: authored by a human (not a bot, not
    # us) and not mentioning the bot. Its content must be non-empty.
    def mentions_bot(m: dict) -> bool:
        return any(u.get("id") == bot_id for u in m.get("mentions", []))

    human = [
        m
        for m in msgs
        if not m.get("author", {}).get("bot")
        and m.get("author", {}).get("id") != bot_id
        and not mentions_bot(m)
    ]
    if not human:
        print(
            "[warn] intent check INCONCLUSIVE: no recent human message in this channel that "
            "doesn't mention the bot.\n"
            "       Post a normal message in the channel and rerun to confirm the intent."
        )
        return
    with_content = [m for m in human if m.get("content")]
    if with_content:
        sample = with_content[0]
        print(
            f"[ok]  Message Content intent is ON "
            f"(read {len(with_content)}/{len(human)} human msgs with content; "
            f"e.g. {sample['author'].get('username','?')}: {sample['content'][:60]!r})"
        )
    else:
        sys.exit(
            f"[FAIL] Message Content intent is OFF. Found {len(human)} human message(s) but every "
            "one has empty content.\n"
            "       Developer Portal -> your app -> Bot -> enable 'Message Content Intent', then rerun."
        )


def post_test(c: httpx.Client, channel_id: str) -> None:
    body = {
        "content": "ale to nie do mnie tak, do mnie nie",
        "allowed_mentions": {"parse": []},  # can never ping anyone, even by accident
    }
    msg = check(c.post(f"/channels/{channel_id}/messages", json=body)).json()
    print(f"[ok]  posted test message id {msg['id']} to channel {channel_id}")


def main() -> None:
    from klaudiusz.config import load_env

    load_env()  # so `uv run smoke.py` picks up .env without a manual source
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        sys.exit("set DISCORD_BOT_TOKEN in the environment")
    if len(sys.argv) != 3:
        sys.exit("usage: DISCORD_BOT_TOKEN=... uv run smoke.py <guild_id> <channel_id>")
    guild_id, channel_id = sys.argv[1], sys.argv[2]

    with client(token) as c:
        me = check(c.get("/users/@me")).json()
        print(f"[ok]  authenticated as {me['username']} (id {me['id']})")
        list_channels(c, guild_id)
        check_intent(c, channel_id, me["id"])
        post_test(c, channel_id)

    print("\nG0 smoke complete. If no [FAIL]/[warn] above, the gate passes.")


if __name__ == "__main__":
    main()
