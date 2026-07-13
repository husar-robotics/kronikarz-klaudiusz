"""`post-newsletter` subcommand: validate links, chunk, post, and archive a daily newsletter."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from . import config as config_module
from .config import Config
from .discord_api import DiscordClient
from .links import _clean_url, validate
from .render import RenderedNewsletter, chunk_newsletter

REPO_ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_DIR_NAME = "newsletters"

# Markdown link or bare URL, whichever comes first; a URL inside `[label](url)`
# is consumed by the first alternative so the second never matches it too.
_LINK_RE = re.compile(r"\[(?P<label>[^\]]+)\]\((?P<url>https?://[^\s)]+)\)|(?P<bare>https?://\S+)")


@dataclass
class PostNewsletterResult:
    """What one `run()` call did, for the CLI handler to report."""

    markdown: str  # link-rewritten
    dropped_links: list[str]
    rendered: RenderedNewsletter
    lead_message_id: str | None
    thread_id: str | None
    archive_path: Path | None


def register(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = subparsers.add_parser(
        "post-newsletter", help="validate links, post, and archive a daily newsletter"
    )
    parser.add_argument("file", help="newsletter markdown file (four ## sections)")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD window the newsletter covers")
    parser.add_argument(
        "--dry-run", action="store_true", help="validate and print the plan; no posting or archive"
    )
    parser.set_defaults(func=_cmd_post_newsletter)


def _cmd_post_newsletter(args: argparse.Namespace) -> int:
    cfg = config_module.load_config()
    path = Path(args.file)
    if not path.is_file():
        sys.exit(f"[FAIL] newsletter file not found: {path}")
    markdown = path.read_text()

    if args.dry_run:
        run(markdown, args.date, cfg, discord_client=None, dry_run=True)
        return 0

    token = config_module.bot_token(require_write=True)
    with DiscordClient(token) as client:
        run(markdown, args.date, cfg, discord_client=client, dry_run=False)
    return 0


def _is_discord_url(url: str) -> bool:
    """Jump URLs our own pipeline generated: a HEAD tells us nothing, so skip validation."""
    host = urlparse(url).hostname or ""
    return host == "discord.com" or host.endswith(".discord.com")


def _extract_urls(markdown: str) -> list[str]:
    """Every URL in markdown links and bare text, deduplicated, in first-seen order."""
    urls: list[str] = []
    seen: set[str] = set()
    for match in _LINK_RE.finditer(markdown):
        url = match.group("url") or _clean_url(match.group("bare"))
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _rewrite_links(markdown: str, dead: set[str]) -> str:
    """Drop dead links: a markdown link falls back to its label; a bare URL gets backticked."""

    def _sub(match: re.Match) -> str:
        if match.group("url"):
            return match.group("label") if match.group("url") in dead else match.group(0)
        raw = match.group("bare")
        url = _clean_url(raw)
        if url not in dead:
            return raw
        trailing = raw[len(url) :]
        return f"`{url}`{trailing}"

    return _LINK_RE.sub(_sub, markdown)


def _validate_and_rewrite_links(
    markdown: str, http_client: httpx.Client | None
) -> tuple[str, list[str]]:
    """Validate every non-discord.com URL and rewrite dead ones out of the markdown.

    Prints one line per dropped link. Returns the rewritten markdown and the
    dropped URLs in the order they first appeared.
    """
    urls = _extract_urls(markdown)
    to_check = [url for url in urls if not _is_discord_url(url)]
    results = validate(to_check, client=http_client) if to_check else {}
    dead = {url for url, ok in results.items() if not ok}
    dropped = [url for url in urls if url in dead]

    for url in dropped:
        print(f"[DROP] dead link removed: {url}")

    return _rewrite_links(markdown, dead), dropped


def _print_dry_run_plan(rendered: RenderedNewsletter, dropped: list[str]) -> None:
    print(f"[DRY RUN] lead: {len(rendered.lead)} chars")
    print(f"[DRY RUN] embed batches: {len(rendered.embed_batches)}")
    for i, batch in enumerate(rendered.embed_batches, start=1):
        print(f"[DRY RUN]   batch {i}: {len(batch)} embed(s)")
    print(f"[DRY RUN] dropped links: {len(dropped)}")


def _archive(markdown: str, date: str, archive_dir: str | Path | None) -> Path:
    directory = Path(archive_dir) if archive_dir is not None else REPO_ROOT / ARCHIVE_DIR_NAME
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{date}.md"
    path.write_text(markdown)
    return path


def run(
    markdown: str,
    date: str,
    cfg: Config,
    discord_client: DiscordClient | None,
    http_client: httpx.Client | None = None,
    dry_run: bool = False,
    archive_dir: str | Path | None = None,
) -> PostNewsletterResult:
    """Validate links, chunk, and (unless `dry_run`) post and archive a newsletter.

    Section validation is `chunk_newsletter`'s job and its `SystemExit` on a
    missing/out-of-order section propagates unchanged. Link validation always
    runs first, so a dead link never reaches Discord even in a dry run.
    """
    rewritten, dropped = _validate_and_rewrite_links(markdown, http_client)
    rendered = chunk_newsletter(rewritten)

    if dry_run:
        _print_dry_run_plan(rendered, dropped)
        return PostNewsletterResult(rewritten, dropped, rendered, None, None, None)

    if discord_client is None:
        raise ValueError("discord_client is required unless dry_run=True")
    channel_id = cfg.discord.newsletter_channel_id
    lead_message = discord_client.post_message(channel_id, content=rendered.lead)
    thread = discord_client.start_thread(channel_id, lead_message["id"], name=f"TL;DR {date}")
    thread_id = thread["id"]
    for batch in rendered.embed_batches:
        discord_client.post_message(thread_id, embeds=batch)

    archive_path = _archive(rewritten, date, archive_dir)

    return PostNewsletterResult(rewritten, dropped, rendered, lead_message["id"], thread_id, archive_path)
