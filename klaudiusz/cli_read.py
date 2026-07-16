"""Read-only CLI subcommands: `channels`, `pull`, `search`, `thread`.

Every handler builds its own `DiscordClient` and calls `config.bot_token()`
lazily, so `klaudiusz --help` and argument-parsing errors never require a
token to be present. Nothing here can write to Discord.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import config as config_module
from .config import Config
from .discord_api import DiscordClient, SearchNotIndexed
from .ingest import display_name, normalize_message, pull_channel, transcript_markdown

_CHANNEL_TYPE_NAMES = {
    DiscordClient.TEXT: "text",
    DiscordClient.ANNOUNCEMENT: "announcement",
    DiscordClient.FORUM: "forum",
}

# Captured at import time: `_find_thread` reads `DiscordClient` at call time
# to build its client, and tests swap that name for a fake with no type
# constants of its own, so the constants themselves must not be looked up
# through it lazily.
_THREAD_PARENT_TYPES = (DiscordClient.TEXT, DiscordClient.ANNOUNCEMENT, DiscordClient.FORUM)

_SINCE_DAYS_RE = re.compile(r"^(\d+)d$")


def register(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    """Wire the four read-only subcommands into the shared parser."""
    _register_channels(subparsers)
    _register_pull(subparsers)
    _register_search(subparsers)
    _register_thread(subparsers)


# -- channels -----------------------------------------------------------------


def _register_channels(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = subparsers.add_parser(
        "channels", help="list the guild's text/announcement/forum channels"
    )
    parser.set_defaults(func=_cmd_channels)


def _cmd_channels(args: argparse.Namespace) -> int:
    cfg = config_module.load_config()
    with DiscordClient(config_module.bot_token()) as client:
        channels = client.guild_channels(cfg.discord.guild_id)

    rows = [
        (ch["name"], ch["id"], _CHANNEL_TYPE_NAMES[ch["type"]])
        for ch in channels
        if ch.get("type") in _CHANNEL_TYPE_NAMES
    ]
    if not rows:
        print("No text/announcement/forum channels found.")
        return 0

    name_width = max(len(row[0]) for row in rows)
    id_width = max(len(row[1]) for row in rows)
    for name, channel_id, kind in rows:
        print(f"{name:<{name_width}}  {channel_id:<{id_width}}  {kind}")
    return 0


# -- pull -----------------------------------------------------------------------


def _register_pull(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = subparsers.add_parser(
        "pull", help="pull one channel's messages (and its threads) since a date"
    )
    parser.add_argument("--channel", required=True, help="channel name (without #) or id")
    parser.add_argument(
        "--since", required=True, help="how far back to pull: 'Nd' (last N days) or 'YYYY-MM-DD'"
    )
    parser.add_argument(
        "--json", action="store_true", help="print JSONL records instead of a markdown transcript"
    )
    parser.set_defaults(func=_cmd_pull)


def _parse_since(value: str, tz: str) -> datetime:
    """'Nd' means N days back from now; 'YYYY-MM-DD' means that date's local midnight."""
    zone = ZoneInfo(tz)
    days_match = _SINCE_DAYS_RE.match(value)
    if days_match:
        return datetime.now(zone) - timedelta(days=int(days_match.group(1)))
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        sys.exit(f"[FAIL] --since must be 'Nd' or 'YYYY-MM-DD', got {value!r}")
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=zone)


def _find_channel(channels: list[dict], name_or_id: str) -> dict:
    bare_name = name_or_id[1:] if name_or_id.startswith("#") else name_or_id
    for ch in channels:
        if ch["id"] == name_or_id or ch.get("name") == bare_name:
            return ch
    sys.exit(f"[FAIL] no channel named or with id {name_or_id!r}")


def _cmd_pull(args: argparse.Namespace) -> int:
    cfg = config_module.load_config()
    with DiscordClient(config_module.bot_token()) as client:
        channels = client.guild_channels(cfg.discord.guild_id)
        channel = _find_channel(channels, args.channel)
        start = _parse_since(args.since, cfg.schedule.timezone)
        end = datetime.now(start.tzinfo)
        records = pull_channel(client, cfg, channel, start, end)

    if args.json:
        for record in records:
            print(json.dumps(record))
    else:
        print(transcript_markdown(records), end="")
    return 0


# -- search -----------------------------------------------------------------


def _register_search(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = subparsers.add_parser("search", help="search the guild's messages")
    parser.add_argument("query", help="search query")
    parser.add_argument("--limit", type=int, default=25, help="max results (default 25)")
    parser.set_defaults(func=_cmd_search)


def _search_hits(result: dict) -> list[dict]:
    """The matched message from each result group (Discord returns match + context per group)."""
    return [group[0] for group in result.get("messages", []) if group]


def _cmd_search(args: argparse.Namespace) -> int:
    cfg = config_module.load_config()
    with DiscordClient(config_module.bot_token()) as client:
        try:
            result = client.search(cfg.discord.guild_id, args.query, limit=args.limit)
        except SearchNotIndexed:
            print(
                "[FAIL] this guild hasn't finished indexing for search yet. Discord indexes a "
                "guild's messages the first time anyone searches it; wait a few minutes and retry."
            )
            return 1

    hits = _search_hits(result)
    if not hits:
        print(f"No results (total_results={result.get('total_results', 0)}).")
        return 0

    print(f"{result.get('total_results', len(hits))} result(s):")
    for msg in hits:
        author = display_name(msg.get("author") or {})
        snippet = (msg.get("content") or "").replace("\n", " ")[:100]
        jump_url = (
            f"https://discord.com/channels/{cfg.discord.guild_id}/{msg['channel_id']}/{msg['id']}"
        )
        print(f"- {author} | channel {msg['channel_id']} | {snippet} | {jump_url}")
    return 0


# -- thread -----------------------------------------------------------------


def _register_thread(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = subparsers.add_parser("thread", help="print the full transcript of one thread")
    parser.add_argument("id", help="thread (channel) id")
    parser.set_defaults(func=_cmd_thread)


def _find_thread(client: DiscordClient, cfg: Config, thread_id: str) -> tuple[dict | None, dict | None]:
    """Best-effort (thread, parent-channel) lookup by scanning active + archived threads.

    There is no "get channel by id" endpoint on DiscordClient, so a thread's
    name and parent are only discoverable by enumerating the guild's threads,
    same as `pull_window` does.
    """
    channels = client.guild_channels(cfg.discord.guild_id)
    in_scope = [ch for ch in channels if ch.get("type") in _THREAD_PARENT_TYPES]
    by_id = {ch["id"]: ch for ch in in_scope}

    for thread in client.active_threads(cfg.discord.guild_id):
        if thread["id"] == thread_id:
            return thread, by_id.get(thread.get("parent_id"))
    for ch in in_scope:
        for thread in client.archived_public_threads(ch["id"]):
            if thread["id"] == thread_id:
                return thread, ch
    return None, None


def _cmd_thread(args: argparse.Namespace) -> int:
    cfg = config_module.load_config()
    with DiscordClient(config_module.bot_token()) as client:
        thread, parent = _find_thread(client, cfg, args.id)
        channel_name = parent["name"] if parent is not None else "unknown"
        thread_name = thread["name"] if thread is not None else None
        records = [
            normalize_message(
                msg,
                channel_id=args.id,
                channel_name=channel_name,
                thread_name=thread_name,
                guild_id=cfg.discord.guild_id,
            )
            for msg in client.messages(args.id)
        ]
    print(transcript_markdown(records), end="")
    return 0
