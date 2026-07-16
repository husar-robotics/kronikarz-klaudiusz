"""The `context` subcommand: assembles the generation-input bundle for one day.

Builds its own `DiscordClient` and calls `config.bot_token()` lazily, same as
`cli_read`, so `klaudiusz --help` and argument-parsing errors never require a
token to be present.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import config as config_module
from .discord_api import DiscordClient
from .ingest import day_window, pull_window, transcript_markdown
from .links import extract_urls, links_markdown, resolve
from .repo_signal import event_count, repo_signal, repo_signal_markdown


def register(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = subparsers.add_parser(
        "context", help="assemble the day's context bundle (transcript, repo signal, links)"
    )
    parser.add_argument("--date", required=True, help="day to build the bundle for, YYYY-MM-DD")
    parser.add_argument(
        "--out", help="output directory (default: ./context-<date>/); must be empty or absent"
    )
    parser.set_defaults(func=_cmd_context)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        sys.exit(f"[FAIL] --date must be YYYY-MM-DD, got {value!r}")


def _prepare_out_dir(out_dir: Path) -> None:
    """Create `out_dir`, refusing to touch a non-empty existing directory."""
    if out_dir.exists():
        if not out_dir.is_dir():
            sys.exit(f"[FAIL] output path {out_dir} exists and is not a directory")
        if any(out_dir.iterdir()):
            sys.exit(f"[FAIL] output directory {out_dir} already exists and is not empty")
    else:
        out_dir.mkdir(parents=True)


def _cmd_context(args: argparse.Namespace) -> int:
    cfg = config_module.load_config()
    day = _parse_date(args.date)
    out_dir = Path(args.out) if args.out else Path(f"./context-{day.isoformat()}")
    _prepare_out_dir(out_dir)

    start, end = day_window(day, cfg.schedule.timezone)

    with DiscordClient(config_module.bot_token()) as client:
        records = pull_window(client, cfg, start, end)

    signal = repo_signal(cfg.shrek_dog.repo, start, end)
    resolved_links = resolve(extract_urls(records))

    message_count = len(records)
    channel_count = len({r["channel_name"] for r in records})
    repo_event_count = event_count(signal)
    quiet = (
        message_count < cfg.schedule.quiet_day_message_threshold and repo_event_count == 0
    )
    meta = {
        "date": day.isoformat(),
        "message_count": message_count,
        "channel_count": channel_count,
        "repo_event_count": repo_event_count,
        "quiet": quiet,
    }

    (out_dir / "transcript.md").write_text(transcript_markdown(records))
    (out_dir / "repo-signal.md").write_text(repo_signal_markdown(signal))
    (out_dir / "links.md").write_text(links_markdown(resolved_links))
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    if quiet:
        print(f"QUIET DAY: {message_count} messages, {repo_event_count} repo events")
        return 2

    print(
        f"context bundle written to {out_dir}: {message_count} messages across "
        f"{channel_count} channels, {repo_event_count} repo events"
    )
    return 0
