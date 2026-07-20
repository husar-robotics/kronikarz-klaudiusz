from __future__ import annotations

import subprocess
from datetime import datetime

import httpx
import pytest
import respx

from klaudiusz import repo_signal as rs

REPO = "husar-robotics/shrek-dog"
API = "https://api.github.com"

WINDOW_START = datetime.fromisoformat("2026-07-11T00:00:00+00:00")
WINDOW_END = datetime.fromisoformat("2026-07-12T00:00:00+00:00")

COMMITS_FIXTURE = [
    {  # before window -> excluded
        "sha": "aaaaaaa0000000000000000000000000000000",
        "commit": {
            "author": {"name": "Ada Lovelace", "date": "2026-07-10T23:59:59Z"},
            "committer": {"name": "Ada Lovelace", "date": "2026-07-10T23:59:59Z"},
            "message": "Prep release notes",
        },
        "author": {"login": "ada-dev"},
        "html_url": f"https://github.com/{REPO}/commit/aaaaaaa0000000000000000000000000000000",
    },
    {  # exactly at start -> included
        "sha": "bbbbbbb1111111111111111111111111111111",
        "commit": {
            "author": {"name": "Ada Lovelace", "date": "2026-07-11T00:00:00Z"},
            "committer": {"name": "Ada Lovelace", "date": "2026-07-11T00:00:00Z"},
            "message": "Fix actuator torque calc\n\nLonger explanation body.",
        },
        "author": {"login": "ada-dev"},
        "html_url": f"https://github.com/{REPO}/commit/bbbbbbb1111111111111111111111111111111",
    },
    {  # inside window, no linked GitHub account -> falls back to commit author name
        "sha": "ccccccc2222222222222222222222222222222",
        "commit": {
            "author": {"name": "Grace Hopper", "date": "2026-07-11T12:00:00Z"},
            "committer": {"name": "Grace Hopper", "date": "2026-07-11T12:00:00Z"},
            "message": "Tune MJX contact params",
        },
        "author": None,
        "html_url": f"https://github.com/{REPO}/commit/ccccccc2222222222222222222222222222222",
    },
    {  # exactly at end -> excluded
        "sha": "ddddddd3333333333333333333333333333333",
        "commit": {
            "author": {"name": "Ada Lovelace", "date": "2026-07-12T00:00:00Z"},
            "committer": {"name": "Ada Lovelace", "date": "2026-07-12T00:00:00Z"},
            "message": "Start next day's work",
        },
        "author": {"login": "ada-dev"},
        "html_url": f"https://github.com/{REPO}/commit/ddddddd3333333333333333333333333333333",
    },
]

# The pulls listing arrives newest-updated first; the walk stops at the first
# PR updated before the window start.
MERGED_PRS_FIXTURE = [
    {
        "number": 44,
        "title": "Unrelated cleanup",
        "user": {"login": "grace"},
        "updated_at": "2026-07-12T00:00:00Z",
        "merged_at": "2026-07-12T00:00:00Z",  # exactly at end -> excluded
        "html_url": f"https://github.com/{REPO}/pull/44",
    },
    {
        "number": 45,
        "title": "Abandoned spike",
        "user": {"login": "grace"},
        "updated_at": "2026-07-11T16:00:00Z",
        "merged_at": None,  # closed without merging -> excluded
        "html_url": f"https://github.com/{REPO}/pull/45",
    },
    {
        "number": 43,
        "title": "Bump MJX pin",
        "user": None,  # deleted account
        "updated_at": "2026-07-11T15:30:00Z",
        "merged_at": "2026-07-11T15:30:00Z",
        "html_url": f"https://github.com/{REPO}/pull/43",
    },
    {
        "number": 42,
        "title": "Switch leg actuators to QDD",
        "user": {"login": "marcinw"},
        "updated_at": "2026-07-11T00:00:00Z",
        "merged_at": "2026-07-11T00:00:00Z",  # exactly at start -> included
        "html_url": f"https://github.com/{REPO}/pull/42",
    },
    {
        "number": 41,
        "title": "Draft QDD comparison",
        "user": {"login": "marcinw"},
        "updated_at": "2026-07-10T18:00:00Z",  # before window -> stops the walk
        "merged_at": "2026-07-10T18:00:00Z",
        "html_url": f"https://github.com/{REPO}/pull/41",
    },
]

# The issues listing arrives newest-created first and interleaves pull
# requests, which carry a `pull_request` key.
OPENED_ISSUES_FIXTURE = [
    {
        "number": 20,
        "title": "next week planning",
        "user": {"login": "marcinw"},
        "created_at": "2026-07-12T00:00:00Z",  # exactly at end -> excluded
        "html_url": f"https://github.com/{REPO}/issues/20",
    },
    {
        "number": 19,
        "title": "flaky MJX contact test",
        "user": {"login": "kate"},
        "created_at": "2026-07-11T23:00:00Z",
        "html_url": f"https://github.com/{REPO}/issues/19",
    },
    {
        "number": 45,
        "title": "Abandoned spike",
        "user": {"login": "grace"},
        "created_at": "2026-07-11T16:00:00Z",
        "html_url": f"https://github.com/{REPO}/pull/45",
        "pull_request": {"url": f"{API}/repos/{REPO}/pulls/45"},  # a PR, not an issue -> skipped
    },
    {
        "number": 18,
        "title": "torque sensor noise on leg 3",
        "user": {"login": "marcinw"},
        "created_at": "2026-07-11T00:00:00Z",  # exactly at start -> included
        "html_url": f"https://github.com/{REPO}/issues/18",
    },
    {
        "number": 17,
        "title": "sim2real friction gap",
        "user": {"login": "grace"},
        "created_at": "2026-07-10T09:00:00Z",  # before window -> stops the walk
        "html_url": f"https://github.com/{REPO}/issues/17",
    },
]


@pytest.fixture(autouse=True)
def token_env(monkeypatch):
    monkeypatch.setenv("HVSR_TOKEN", "unit-test-token")


def _mock_github(commits=(), pulls=(), issues=()):
    """Route the three listing endpoints to canned single-page responses."""
    routes = {
        "commits": respx.get(f"{API}/repos/{REPO}/commits").mock(
            return_value=httpx.Response(200, json=list(commits))
        ),
        "pulls": respx.get(f"{API}/repos/{REPO}/pulls").mock(
            return_value=httpx.Response(200, json=list(pulls))
        ),
        "issues": respx.get(f"{API}/repos/{REPO}/issues").mock(
            return_value=httpx.Response(200, json=list(issues))
        ),
    }
    return routes


# -- commits ---------------------------------------------------------------------


@respx.mock
def test_commits_filters_window_and_shapes_records():
    _mock_github(commits=COMMITS_FIXTURE)

    result = rs.commits(REPO, WINDOW_START, WINDOW_END)

    assert [c["sha"] for c in result] == ["bbbbbbb", "ccccccc"]
    assert result[0]["author"] == "ada-dev"
    assert result[0]["message"] == "Fix actuator torque calc"
    assert result[0]["url"] == f"https://github.com/{REPO}/commit/bbbbbbb1111111111111111111111111111111"
    assert result[1]["author"] == "Grace Hopper"  # no linked GitHub account -> commit author name


@respx.mock
def test_commits_sends_window_params_and_bearer_token():
    routes = _mock_github()

    rs.commits(REPO, WINDOW_START, WINDOW_END)

    request = routes["commits"].calls.last.request
    assert request.headers["Authorization"] == "Bearer unit-test-token"
    assert request.url.params["since"] == "2026-07-11T00:00:00Z"
    assert request.url.params["until"] == "2026-07-12T00:00:00Z"


@respx.mock
def test_commits_follow_link_header_pagination():
    page2_url = f"{API}/repos/{REPO}/commits?page=2"
    respx.get(f"{API}/repos/{REPO}/commits").mock(
        side_effect=[
            httpx.Response(
                200,
                json=[COMMITS_FIXTURE[1]],
                headers={"Link": f'<{page2_url}>; rel="next"'},
            ),
            httpx.Response(200, json=[COMMITS_FIXTURE[2]]),
        ]
    )

    result = rs.commits(REPO, WINDOW_START, WINDOW_END)

    assert [c["sha"] for c in result] == ["bbbbbbb", "ccccccc"]


# -- merged PRs ------------------------------------------------------------------


@respx.mock
def test_merged_prs_filters_window_boundaries_and_unmerged():
    _mock_github(pulls=MERGED_PRS_FIXTURE)

    result = rs.merged_prs(REPO, WINDOW_START, WINDOW_END)

    assert [pr["number"] for pr in result] == [43, 42]
    assert result[0]["author"] == "unknown"  # deleted account -> user is null
    assert result[1]["author"] == "marcinw"


@respx.mock
def test_merged_prs_stop_paginating_past_the_window():
    page2 = respx.get(f"{API}/repos/{REPO}/pulls", params={"page": "2"}).mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get(f"{API}/repos/{REPO}/pulls").mock(
        return_value=httpx.Response(
            200,
            json=MERGED_PRS_FIXTURE,  # ends with a PR updated before the window
            headers={"Link": f'<{API}/repos/{REPO}/pulls?page=2>; rel="next"'},
        )
    )

    result = rs.merged_prs(REPO, WINDOW_START, WINDOW_END)

    assert [pr["number"] for pr in result] == [43, 42]
    assert not page2.called


# -- opened issues ---------------------------------------------------------------


@respx.mock
def test_opened_issues_filters_window_and_skips_pull_requests():
    routes = _mock_github(issues=OPENED_ISSUES_FIXTURE)

    result = rs.opened_issues(REPO, WINDOW_START, WINDOW_END)

    assert [issue["number"] for issue in result] == [19, 18]
    assert routes["issues"].calls.last.request.url.params["state"] == "all"


# -- bundling --------------------------------------------------------------------


@respx.mock
def test_repo_signal_bundles_all_three():
    _mock_github(
        commits=COMMITS_FIXTURE, pulls=MERGED_PRS_FIXTURE, issues=OPENED_ISSUES_FIXTURE
    )

    signal = rs.repo_signal(REPO, WINDOW_START, WINDOW_END)

    assert set(signal) == {"commits", "merged_prs", "opened_issues"}
    assert len(signal["commits"]) == 2
    assert len(signal["merged_prs"]) == 2
    assert len(signal["opened_issues"]) == 2
    assert rs.event_count(signal) == 6


@respx.mock
def test_repo_signal_empty_window():
    _mock_github()

    signal = rs.repo_signal(REPO, WINDOW_START, WINDOW_END)

    assert signal == {"commits": [], "merged_prs": [], "opened_issues": []}
    assert rs.event_count(signal) == 0


# -- failure modes ---------------------------------------------------------------


@respx.mock
def test_forbidden_names_the_token_variable():
    respx.get(f"{API}/repos/{REPO}/commits").mock(
        return_value=httpx.Response(403, json={"message": "Resource not accessible"})
    )

    with pytest.raises(SystemExit) as excinfo:
        rs.commits(REPO, WINDOW_START, WINDOW_END)

    message = str(excinfo.value)
    assert "403" in message
    assert "HVSR_TOKEN" in message


@respx.mock
def test_server_error_exits_loudly_with_body():
    respx.get(f"{API}/repos/{REPO}/pulls").mock(
        return_value=httpx.Response(500, text="upstream exploded")
    )

    with pytest.raises(SystemExit) as excinfo:
        rs.merged_prs(REPO, WINDOW_START, WINDOW_END)

    message = str(excinfo.value)
    assert "500" in message
    assert "upstream exploded" in message


@respx.mock
def test_network_error_exits_loudly():
    respx.get(f"{API}/repos/{REPO}/issues").mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    with pytest.raises(SystemExit) as excinfo:
        rs.opened_issues(REPO, WINDOW_START, WINDOW_END)

    assert "connection refused" in str(excinfo.value)


# -- token resolution ------------------------------------------------------------


def test_env_token_wins_without_touching_gh(monkeypatch):
    monkeypatch.setattr(
        rs.subprocess,
        "run",
        lambda *a, **k: pytest.fail("gh must not run when the env token is set"),
    )

    assert rs.github_token() == "unit-test-token"


def test_token_falls_back_to_gh_auth_token(monkeypatch):
    monkeypatch.delenv("HVSR_TOKEN")
    monkeypatch.setattr(
        rs.subprocess,
        "run",
        lambda cmd, **k: subprocess.CompletedProcess(cmd, 0, stdout="gh-local-token\n", stderr=""),
    )

    assert rs.github_token() == "gh-local-token"


def test_missing_token_and_missing_gh_fail_loudly(monkeypatch):
    monkeypatch.delenv("HVSR_TOKEN")

    def no_gh(*args, **kwargs):
        raise FileNotFoundError("gh")

    monkeypatch.setattr(rs.subprocess, "run", no_gh)

    with pytest.raises(SystemExit) as excinfo:
        rs.github_token()

    assert "HVSR_TOKEN" in str(excinfo.value)


# -- markdown --------------------------------------------------------------------


@respx.mock
def test_repo_signal_markdown_populated_snapshot():
    _mock_github(
        commits=COMMITS_FIXTURE, pulls=MERGED_PRS_FIXTURE, issues=OPENED_ISSUES_FIXTURE
    )
    signal = rs.repo_signal(REPO, WINDOW_START, WINDOW_END)

    markdown = rs.repo_signal_markdown(signal)

    expected = (
        "## Commits\n\n"
        f"- [bbbbbbb](https://github.com/{REPO}/commit/bbbbbbb1111111111111111111111111111111)"
        " Fix actuator torque calc — ada-dev\n"
        f"- [ccccccc](https://github.com/{REPO}/commit/ccccccc2222222222222222222222222222222)"
        " Tune MJX contact params — Grace Hopper\n"
        "\n"
        "## Merged PRs\n\n"
        f"- [#43](https://github.com/{REPO}/pull/43) Bump MJX pin — unknown\n"
        f"- [#42](https://github.com/{REPO}/pull/42) Switch leg actuators to QDD — marcinw\n"
        "\n"
        "## Opened issues\n\n"
        f"- [#19](https://github.com/{REPO}/issues/19) flaky MJX contact test — kate\n"
        f"- [#18](https://github.com/{REPO}/issues/18) torque sensor noise on leg 3 — marcinw"
    )
    assert markdown == expected


def test_repo_signal_markdown_empty():
    signal = {"commits": [], "merged_prs": [], "opened_issues": []}

    assert rs.repo_signal_markdown(signal) == "No repo activity in this window."
