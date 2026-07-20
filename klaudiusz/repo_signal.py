"""shrek-dog activity for a date window (commits, merged PRs, opened issues), via the GitHub REST API.

The daily routine's cloud environment has no `gh` CLI, so this module talks to
api.github.com directly with httpx. Auth comes from HVSR_TOKEN (the same
fine-grained PAT `publish-log` uses), read from the environment — the
repo-root .env is folded in at CLI entry by `load_env`. Local runs without a
token fall back to `gh auth token` when gh happens to be installed and
authenticated.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from datetime import datetime, timezone

import httpx

from . import config as config_module

_API = "https://api.github.com"
_PER_PAGE = 100
# Well above what a single day's activity could ever reach; bounds the
# newest-first listing walks the way the old `gh --limit 500` did.
_MAX_ITEMS = 500
_TIMEOUT = 30.0


def _gh_auth_token() -> str | None:
    """Best-effort token from a locally installed `gh`; None when unavailable."""
    try:
        result = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        return None
    token = result.stdout.strip()
    return token if result.returncode == 0 and token else None


def github_token() -> str:
    """HVSR_TOKEN from the environment or .env, else `gh auth token`, else a loud exit."""
    token = config_module.hvsr_token() or _gh_auth_token()
    if not token:
        sys.exit(
            "[FAIL] set HVSR_TOKEN in the environment or repo-root .env "
            "(fine-grained PAT with read access to shrek-dog)"
        )
    return token


def _client(token: str) -> httpx.Client:
    return httpx.Client(
        base_url=_API,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=_TIMEOUT,
    )


def _get(client: httpx.Client, url: str, params: dict | None = None) -> httpx.Response:
    """GET or exit loudly with a distinct message per failure mode."""
    try:
        response = client.get(url, params=params)
    except httpx.HTTPError as exc:
        sys.exit(f"[FAIL] GitHub API request failed: {exc}")
    if response.status_code in (401, 403, 404):
        sys.exit(
            f"[FAIL] GitHub API GET {response.request.url.path} returned "
            f"{response.status_code}; check that HVSR_TOKEN grants read on "
            "contents, pull requests, and issues (a private repo 404s without access)"
        )
    if response.is_error:
        sys.exit(
            f"[FAIL] GitHub API GET {response.request.url.path} returned "
            f"{response.status_code}: {response.text[:200]}"
        )
    return response


def _paginate(client: httpx.Client, path: str, params: dict) -> Iterator[dict]:
    """Yield items across Link-header pages; a consumer that breaks early also stops fetching."""
    url: str | None = path
    fetched = 0
    while url is not None and fetched < _MAX_ITEMS:
        response = _get(client, url, params)
        params = None  # the rel="next" URL already carries the full query string
        items = response.json()
        yield from items
        fetched += len(items)
        url = response.links.get("next", {}).get("url")


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
    params = {"since": _iso(start), "until": _iso(end), "per_page": _PER_PAGE}
    out = []
    with _client(github_token()) as client:
        for c in _paginate(client, f"/repos/{repo}/commits", params):
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
    """Merged PRs of `repo` with merged_at in [start, end).

    The listing is walked newest-updated first and stops at the first PR
    updated before `start`: merged_at never exceeds updated_at, so nothing
    merged in the window can appear past that point.
    """
    params = {"state": "closed", "sort": "updated", "direction": "desc", "per_page": _PER_PAGE}
    out = []
    with _client(github_token()) as client:
        for pr in _paginate(client, f"/repos/{repo}/pulls", params):
            if datetime.fromisoformat(pr["updated_at"]) < start:
                break
            if not pr.get("merged_at"):
                continue  # closed without merging
            if not _in_window(datetime.fromisoformat(pr["merged_at"]), start, end):
                continue
            out.append(
                {
                    "number": pr["number"],
                    "title": pr["title"],
                    "author": (pr.get("user") or {}).get("login") or "unknown",
                    "url": pr["html_url"],
                }
            )
    return out


def opened_issues(repo: str, start: datetime, end: datetime) -> list[dict]:
    """Issues of `repo` opened (created_at) in [start, end).

    `state=all` is required so an issue opened and closed within the window is
    not silently dropped. The issues endpoint interleaves pull requests; those
    carry a `pull_request` key and are skipped. The walk is newest-created
    first and stops at the first issue created before `start`.
    """
    params = {"state": "all", "sort": "created", "direction": "desc", "per_page": _PER_PAGE}
    out = []
    with _client(github_token()) as client:
        for issue in _paginate(client, f"/repos/{repo}/issues", params):
            created_at = datetime.fromisoformat(issue["created_at"])
            if created_at < start:
                break
            if "pull_request" in issue:
                continue
            if not _in_window(created_at, start, end):
                continue
            out.append(
                {
                    "number": issue["number"],
                    "title": issue["title"],
                    "author": (issue.get("user") or {}).get("login") or "unknown",
                    "url": issue["html_url"],
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
