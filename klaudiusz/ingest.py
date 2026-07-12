"""Windowed pull of a guild's messages into the shared record shape, plus a markdown transcript."""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .config import Config
from .discord_api import DiscordAPIError, DiscordClient

DISCORD_EPOCH_MS = 1420070400000

_MESSAGE_CHANNEL_TYPES = (DiscordClient.TEXT, DiscordClient.ANNOUNCEMENT)
_THREAD_PARENT_TYPES = (DiscordClient.TEXT, DiscordClient.ANNOUNCEMENT, DiscordClient.FORUM)


def day_window(day: date, tz: str) -> tuple[datetime, datetime]:
    """The [00:00, 24:00) window of `day` in the `tz` timezone, as aware datetimes."""
    zone = ZoneInfo(tz)
    start = datetime(day.year, day.month, day.day, tzinfo=zone)
    return start, start + timedelta(days=1)


def _snowflake(dt: datetime) -> str:
    unix_ms = int(dt.timestamp() * 1000)
    return str((unix_ms - DISCORD_EPOCH_MS) << 22)


def window_snowflakes(start: datetime, end: datetime) -> tuple[str, str]:
    """Convert a [start, end) datetime window to (after, before) snowflake strings.

    Discord's `after` is exclusive, so `after` is the start snowflake minus
    one; a message stamped exactly at the window's first millisecond is
    included.
    """
    return str(int(_snowflake(start)) - 1), _snowflake(end)


def display_name(author: dict) -> str:
    """The record's `author` field: global_name if set, else username."""
    return author.get("global_name") or author.get("username", "")


def normalize_message(
    msg: dict,
    *,
    channel_id: str,
    channel_name: str,
    thread_name: str | None,
    guild_id: str,
) -> dict:
    """Turn one raw Discord message into the shared message record.

    `channel_id` is the id of the message's immediate container: a text or
    announcement channel, or a thread. Discord jump URLs use that same id as
    their channel component, even when the container is a thread, so it
    doubles as the id `jump_url` is built from.
    """
    author = msg.get("author") or {}
    attachment_urls = [a["url"] for a in msg.get("attachments", []) if a.get("url")]
    return {
        "id": msg["id"],
        "channel_id": channel_id,
        "channel_name": channel_name,
        "thread_name": thread_name,
        "author": display_name(author),
        "author_is_bot": bool(author.get("bot", False)),
        "timestamp": msg.get("timestamp", ""),
        "content": msg.get("content", ""),
        "attachment_urls": attachment_urls,
        "jump_url": f"https://discord.com/channels/{guild_id}/{channel_id}/{msg['id']}",
    }


def _skip_no_access(exc: DiscordAPIError, label: str) -> None:
    """Re-raise anything but a 403.

    The guild channel list includes channels whose permission overwrites deny
    the bot access (verified live 2026-07-12: /guilds/{id}/channels returns
    them, then their /messages returns 403 code 50001), so a per-container
    403 means "not ours to read", never a pipeline failure.
    """
    if exc.status_code != 403:
        raise exc
    print(f"[warn] skipping {label}: bot has no access (403)", file=sys.stderr)


def _plain_channel_messages(
    client: DiscordClient, config: Config, channel: dict, after: str, before: str
) -> list[dict]:
    """Messages posted directly in `channel` (nothing for forum channels, which hold only threads)."""
    if channel.get("type") not in _MESSAGE_CHANNEL_TYPES:
        return []
    try:
        msgs = list(client.messages(channel["id"], after=after, before=before))
    except DiscordAPIError as exc:
        _skip_no_access(exc, f"#{channel['name']}")
        return []
    return [
        normalize_message(
            msg,
            channel_id=channel["id"],
            channel_name=channel["name"],
            thread_name=None,
            guild_id=config.discord.guild_id,
        )
        for msg in msgs
    ]


def _is_stale_archived(thread: dict, after_int: int) -> bool:
    """True when an archived thread's last message predates the window (nothing to pull)."""
    last_message_id = thread.get("last_message_id")
    return last_message_id is not None and int(last_message_id) < after_int


def _thread_messages(
    client: DiscordClient,
    config: Config,
    channel: dict,
    active_threads: list[dict],
    after: str,
    before: str,
) -> list[dict]:
    """Messages from every thread of `channel` (active or archived) that can fall in the window."""
    after_int, before_int = int(after), int(before)
    guild_id = config.discord.guild_id

    active_here = [
        t
        for t in active_threads
        if t.get("parent_id") == channel["id"] and t.get("type") == DiscordClient.PUBLIC_THREAD
    ]
    try:
        archived_here = [
            t
            for t in client.archived_public_threads(channel["id"])
            if not _is_stale_archived(t, after_int)
        ]
    except DiscordAPIError as exc:
        _skip_no_access(exc, f"archived threads of #{channel['name']}")
        archived_here = []

    records: list[dict] = []
    seen_ids: set[str] = set()
    for thread in (*active_here, *archived_here):
        thread_id = thread["id"]
        if thread_id in seen_ids or int(thread_id) >= before_int:
            # a thread created at/after the window's end cannot hold an
            # in-window message, since every message in it postdates it
            continue
        seen_ids.add(thread_id)
        try:
            thread_msgs = list(client.messages(thread_id, after=after, before=before))
        except DiscordAPIError as exc:
            _skip_no_access(exc, f"thread {thread.get('name', thread_id)!r}")
            continue
        for msg in thread_msgs:
            records.append(
                normalize_message(
                    msg,
                    channel_id=thread_id,
                    channel_name=channel["name"],
                    thread_name=thread.get("name"),
                    guild_id=guild_id,
                )
            )
    return records


def pull_channel(
    client: DiscordClient, config: Config, channel: dict, start: datetime, end: datetime
) -> list[dict]:
    """One channel's messages, plus every thread of it, for [start, end)."""
    after, before = window_snowflakes(start, end)
    active_threads = client.active_threads(config.discord.guild_id)

    records = _plain_channel_messages(client, config, channel, after, before)
    records += _thread_messages(client, config, channel, active_threads, after, before)

    records.sort(key=lambda r: int(r["id"]))
    return records


def pull_window(client: DiscordClient, config: Config, start: datetime, end: datetime) -> list[dict]:
    """The whole guild's messages for [start, end): text/announcement channels and forum threads.

    Channels named in `config.discord.ignore_channels` are skipped entirely,
    including any threads parented to them.
    """
    all_channels = client.guild_channels(config.discord.guild_id)
    ignore = set(config.discord.ignore_channels)
    in_scope = [
        ch
        for ch in all_channels
        if ch.get("type") in _THREAD_PARENT_TYPES and ch.get("name") not in ignore
    ]

    after, before = window_snowflakes(start, end)
    active_threads = client.active_threads(config.discord.guild_id)

    records: list[dict] = []
    for channel in in_scope:
        records += _plain_channel_messages(client, config, channel, after, before)
        records += _thread_messages(client, config, channel, active_threads, after, before)

    records.sort(key=lambda r: int(r["id"]))
    return records


def _format_time(timestamp: str) -> str:
    return datetime.fromisoformat(timestamp).strftime("%H:%M")


def _message_line(record: dict) -> str:
    parts = [f"- **{record['author']}**"]
    if record["author_is_bot"]:
        parts.append("[bot]")
    parts.append(f"({_format_time(record['timestamp'])})")
    content_lines = record["content"].splitlines()
    first, rest = (content_lines[0], content_lines[1:]) if content_lines else ("", [])
    if first:
        parts.append(first)
    parts.append(f"[↗]({record['jump_url']})")
    line = " ".join(parts)
    if rest:
        line += "\n" + "\n".join(f"  {rest_line}" for rest_line in rest)
    return line


def transcript_markdown(records: list[dict]) -> str:
    """Group `records` by channel, then thread, chronological within each group.

    Plain channel messages come before that channel's thread subsections.
    Channel and thread order follows first appearance in `records`, which is
    chronological order when `records` comes from `pull_window`/`pull_channel`.
    """
    if not records:
        return "No messages in this window.\n"

    channels: dict[str, dict] = {}
    order: list[str] = []
    for record in records:
        name = record["channel_name"]
        if name not in channels:
            channels[name] = {"plain": [], "threads": {}}
            order.append(name)
        bucket = channels[name]
        thread_name = record["thread_name"]
        if thread_name is None:
            bucket["plain"].append(record)
        else:
            bucket["threads"].setdefault(thread_name, []).append(record)

    sections = []
    for name in order:
        bucket = channels[name]
        lines = [f"## #{name}"]
        lines.extend(_message_line(r) for r in bucket["plain"])
        for thread_name, thread_records in bucket["threads"].items():
            lines.append(f"### thread: {thread_name}")
            lines.extend(_message_line(r) for r in thread_records)
        sections.append("\n".join(lines))
    return "\n\n".join(sections) + "\n"
