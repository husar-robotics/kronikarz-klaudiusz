"""shrek-dog activity for a date window (commits, merged PRs, opened issues), via `gh`."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone

# Well above what a single day's PR/issue volume could ever reach; keeps a
# single `gh` call sufficient without needing to paginate these ourselves.
_LIST_LIMIT = 500


def _run_gh(args: list[str]) -> str:
    """Run `gh` and return stdout, or exit loudly with a distinct message per failure mode."""
    try:
        result = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        sys.exit("[FAIL] gh CLI not found; install it and run `gh auth login`")
    if result.returncode != 0:
        sys.exit(f"[FAIL] gh {' '.join(args)} exited {result.returncode}: {result.stderr.strip()}")
    return result.stdout


def _load(stdout: str) -> list[dict]:
    return json.loads(stdout) if stdout.strip() else []


def _iso(dt: datetime) -> str:
    """UTC ISO 8601 with a Z suffix, the form the GitHub API expects for since/until."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _in_window(dt: datetime, start: datetime, end: datetime) -> bool:
    return start <= dt < end


def commits(repo: str, start: datetime, end: datetime) -> list[dict]:
    """Commits on the default branch of `repo` in [start, end).

    `since`/`until` narrow the request server-side. Results are also filtered
    client-side on the committer date, because GitHub does not document the
    since/until boundary inclusivity precisely enough to rely on it alone for
    a half-open window.
    """
    # --method GET is load-bearing: `gh api` switches to POST as soon as any
    # -f field is present, and GETs with -f fields only stay GETs (with the
    # fields moved to the query string) when the method is forced.
    stdout = _run_gh(
        [
            "api",
            "--method",
            "GET",
            f"repos/{repo}/commits",
            "--paginate",
            "-f",
            f"since={_iso(start)}",
            "-f",
            f"until={_iso(end)}",
        ]
    )
    out = []
    for c in _load(stdout):
        date = datetime.fromisoformat(c["commit"]["committer"]["date"])
        if not _in_window(date, start, end):
            continue
        author = (c.get("author") or {}).get("login") or c["commit"]["author"]["name"]
        message = c["commit"]["message"]
        out.append(
            {
                "sha": c["sha"][:7],
                "author": author,
                "message": message.splitlines()[0] if message else "",
                "url": c["html_url"],
            }
        )
    return out


def merged_prs(repo: str, start: datetime, end: datetime) -> list[dict]:
    """Merged PRs of `repo` with mergedAt in [start, end)."""
    stdout = _run_gh(
        [
            "pr",
            "list",
            "--repo",
            repo,
            "--state",
            "merged",
            "--json",
            "number,title,author,mergedAt,url",
            "--limit",
            str(_LIST_LIMIT),
        ]
    )
    out = []
    for pr in _load(stdout):
        merged_at = datetime.fromisoformat(pr["mergedAt"])
        if not _in_window(merged_at, start, end):
            continue
        out.append(
            {
                "number": pr["number"],
                "title": pr["title"],
                "author": (pr.get("author") or {}).get("login") or "unknown",
                "url": pr["url"],
            }
        )
    return out


def opened_issues(repo: str, start: datetime, end: datetime) -> list[dict]:
    """Issues of `repo` opened (createdAt) in [start, end).

    `--state all` is required: `gh issue list` defaults to open issues only,
    which would silently drop any issue opened and closed within the window.
    """
    stdout = _run_gh(
        [
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "all",
            "--json",
            "number,title,author,createdAt,url",
            "--limit",
            str(_LIST_LIMIT),
        ]
    )
    out = []
    for issue in _load(stdout):
        created_at = datetime.fromisoformat(issue["createdAt"])
        if not _in_window(created_at, start, end):
            continue
        out.append(
            {
                "number": issue["number"],
                "title": issue["title"],
                "author": (issue.get("author") or {}).get("login") or "unknown",
                "url": issue["url"],
            }
        )
    return out


def repo_signal(repo: str, start: datetime, end: datetime) -> dict:
    """Bundle commits, merged PRs, and opened issues for the window."""
    return {
        "commits": commits(repo, start, end),
        "merged_prs": merged_prs(repo, start, end),
        "opened_issues": opened_issues(repo, start, end),
    }


def event_count(signal: dict) -> int:
    """Total events across all categories; feeds the quiet-day rule."""
    return sum(len(signal[key]) for key in ("commits", "merged_prs", "opened_issues"))


_SECTION_TITLES = {
    "commits": "Commits",
    "merged_prs": "Merged PRs",
    "opened_issues": "Opened issues",
}


def _commit_line(c: dict) -> str:
    return f"- [{c['sha']}]({c['url']}) {c['message']} — {c['author']}"


def _numbered_line(item: dict) -> str:
    return f"- [#{item['number']}]({item['url']}) {item['title']} — {item['author']}"


_LINE_RENDERERS = {
    "commits": _commit_line,
    "merged_prs": _numbered_line,
    "opened_issues": _numbered_line,
}


def repo_signal_markdown(signal: dict) -> str:
    """Render `repo-signal.md`: one H2 per non-empty category, one line per event."""
    if event_count(signal) == 0:
        return "No repo activity in this window."

    sections = []
    for key in ("commits", "merged_prs", "opened_issues"):
        events = signal[key]
        if not events:
            continue
        render_line = _LINE_RENDERERS[key]
        lines = "\n".join(render_line(e) for e in events)
        sections.append(f"## {_SECTION_TITLES[key]}\n\n{lines}")
    return "\n\n".join(sections)
