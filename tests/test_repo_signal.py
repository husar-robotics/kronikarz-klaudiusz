from __future__ import annotations

import json
import subprocess
from datetime import datetime

import pytest

from klaudiusz import repo_signal as rs

REPO = "husar-robotics/shrek-dog"

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

MERGED_PRS_FIXTURE = [
    {
        "number": 41,
        "title": "Draft QDD comparison",
        "author": {"id": "u1", "is_bot": False, "login": "marcinw"},
        "mergedAt": "2026-07-10T18:00:00Z",  # before window -> excluded
        "url": f"https://github.com/{REPO}/pull/41",
    },
    {
        "number": 42,
        "title": "Switch leg actuators to QDD",
        "author": {"id": "u1", "is_bot": False, "login": "marcinw"},
        "mergedAt": "2026-07-11T00:00:00Z",  # exactly at start -> included
        "url": f"https://github.com/{REPO}/pull/42",
    },
    {
        "number": 43,
        "title": "Bump MJX pin",
        "author": None,  # deleted account
        "mergedAt": "2026-07-11T15:30:00Z",
        "url": f"https://github.com/{REPO}/pull/43",
    },
    {
        "number": 44,
        "title": "Unrelated cleanup",
        "author": {"id": "u2", "is_bot": False, "login": "grace"},
        "mergedAt": "2026-07-12T00:00:00Z",  # exactly at end -> excluded
        "url": f"https://github.com/{REPO}/pull/44",
    },
]

OPENED_ISSUES_FIXTURE = [
    {
        "number": 17,
        "title": "sim2real friction gap",
        "author": {"id": "u2", "is_bot": False, "login": "grace"},
        "createdAt": "2026-07-10T09:00:00Z",  # before window -> excluded
        "url": f"https://github.com/{REPO}/issues/17",
    },
    {
        "number": 18,
        "title": "torque sensor noise on leg 3",
        "author": {"id": "u1", "is_bot": False, "login": "marcinw"},
        "createdAt": "2026-07-11T00:00:00Z",  # exactly at start -> included
        "url": f"https://github.com/{REPO}/issues/18",
    },
    {
        "number": 19,
        "title": "flaky MJX contact test",
        "author": {"id": "u3", "is_bot": False, "login": "kate"},
        "createdAt": "2026-07-11T23:00:00Z",
        "url": f"https://github.com/{REPO}/issues/19",
    },
    {
        "number": 20,
        "title": "next week planning",
        "author": {"id": "u1", "is_bot": False, "login": "marcinw"},
        "createdAt": "2026-07-12T00:00:00Z",  # exactly at end -> excluded
        "url": f"https://github.com/{REPO}/issues/20",
    },
]

ALL_FIXTURES = {
    "commits": COMMITS_FIXTURE,
    "merged_prs": MERGED_PRS_FIXTURE,
    "opened_issues": OPENED_ISSUES_FIXTURE,
}

EMPTY_FIXTURES = {"commits": [], "merged_prs": [], "opened_issues": []}


def _completed(stdout: str, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["gh"], returncode=returncode, stdout=stdout, stderr=stderr)


def _fake_run(fixtures: dict[str, list[dict]]):
    """Route a mocked subprocess.run by the gh subcommand (`args[1]`)."""

    def run(cmd, **kwargs):
        assert cmd[0] == "gh"
        if cmd[1] == "api":
            return _completed(json.dumps(fixtures["commits"]))
        if cmd[1] == "pr":
            return _completed(json.dumps(fixtures["merged_prs"]))
        if cmd[1] == "issue":
            return _completed(json.dumps(fixtures["opened_issues"]))
        raise AssertionError(f"unexpected gh subcommand: {cmd}")

    return run


def test_commits_filters_window_and_shapes_records(monkeypatch):
    monkeypatch.setattr(rs.subprocess, "run", _fake_run(ALL_FIXTURES))

    result = rs.commits(REPO, WINDOW_START, WINDOW_END)

    assert [c["sha"] for c in result] == ["bbbbbbb", "ccccccc"]
    assert result[0]["author"] == "ada-dev"
    assert result[0]["message"] == "Fix actuator torque calc"
    assert result[0]["url"] == f"https://github.com/{REPO}/commit/bbbbbbb1111111111111111111111111111111"
    assert result[1]["author"] == "Grace Hopper"  # no linked GitHub account -> commit author name


def test_commits_passes_since_until_query_params(monkeypatch):
    seen = {}

    def run(cmd, **kwargs):
        seen["cmd"] = cmd
        return _completed(json.dumps([]))

    monkeypatch.setattr(rs.subprocess, "run", run)

    rs.commits(REPO, WINDOW_START, WINDOW_END)

    cmd = seen["cmd"]
    assert cmd[:4] == ["gh", "api", f"repos/{REPO}/commits", "--paginate"]
    assert "since=2026-07-11T00:00:00Z" in cmd
    assert "until=2026-07-12T00:00:00Z" in cmd


def test_merged_prs_filters_window_boundaries(monkeypatch):
    monkeypatch.setattr(rs.subprocess, "run", _fake_run(ALL_FIXTURES))

    result = rs.merged_prs(REPO, WINDOW_START, WINDOW_END)

    assert [pr["number"] for pr in result] == [42, 43]
    assert result[0]["author"] == "marcinw"
    assert result[1]["author"] == "unknown"  # deleted account -> author is null


def test_opened_issues_filters_window_boundaries(monkeypatch):
    monkeypatch.setattr(rs.subprocess, "run", _fake_run(ALL_FIXTURES))

    result = rs.opened_issues(REPO, WINDOW_START, WINDOW_END)

    assert [issue["number"] for issue in result] == [18, 19]


def test_opened_issues_requests_all_states(monkeypatch):
    seen = {}

    def run(cmd, **kwargs):
        seen["cmd"] = cmd
        return _completed(json.dumps([]))

    monkeypatch.setattr(rs.subprocess, "run", run)

    rs.opened_issues(REPO, WINDOW_START, WINDOW_END)

    cmd = seen["cmd"]
    assert cmd[cmd.index("--state") + 1] == "all"


def test_repo_signal_bundles_all_three(monkeypatch):
    monkeypatch.setattr(rs.subprocess, "run", _fake_run(ALL_FIXTURES))

    signal = rs.repo_signal(REPO, WINDOW_START, WINDOW_END)

    assert set(signal) == {"commits", "merged_prs", "opened_issues"}
    assert len(signal["commits"]) == 2
    assert len(signal["merged_prs"]) == 2
    assert len(signal["opened_issues"]) == 2


def test_repo_signal_empty_window(monkeypatch):
    monkeypatch.setattr(rs.subprocess, "run", _fake_run(EMPTY_FIXTURES))

    signal = rs.repo_signal(REPO, WINDOW_START, WINDOW_END)

    assert signal == {"commits": [], "merged_prs": [], "opened_issues": []}
    assert rs.event_count(signal) == 0


def test_event_count(monkeypatch):
    monkeypatch.setattr(rs.subprocess, "run", _fake_run(ALL_FIXTURES))

    signal = rs.repo_signal(REPO, WINDOW_START, WINDOW_END)

    assert rs.event_count(signal) == 6


def test_gh_missing_exits_loudly(monkeypatch):
    def run(cmd, **kwargs):
        raise FileNotFoundError("gh")

    monkeypatch.setattr(rs.subprocess, "run", run)

    with pytest.raises(SystemExit) as excinfo:
        rs.commits(REPO, WINDOW_START, WINDOW_END)

    message = str(excinfo.value).lower()
    assert "gh" in message
    assert "not found" in message


def test_gh_failure_exits_loudly_with_stderr(monkeypatch):
    def run(cmd, **kwargs):
        return _completed("", returncode=1, stderr="gh: authentication required. Run `gh auth login`.")

    monkeypatch.setattr(rs.subprocess, "run", run)

    with pytest.raises(SystemExit) as excinfo:
        rs.merged_prs(REPO, WINDOW_START, WINDOW_END)

    assert "authentication required" in str(excinfo.value)


def test_repo_signal_markdown_populated_snapshot(monkeypatch):
    monkeypatch.setattr(rs.subprocess, "run", _fake_run(ALL_FIXTURES))
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
        f"- [#42](https://github.com/{REPO}/pull/42) Switch leg actuators to QDD — marcinw\n"
        f"- [#43](https://github.com/{REPO}/pull/43) Bump MJX pin — unknown\n"
        "\n"
        "## Opened issues\n\n"
        f"- [#18](https://github.com/{REPO}/issues/18) torque sensor noise on leg 3 — marcinw\n"
        f"- [#19](https://github.com/{REPO}/issues/19) flaky MJX contact test — kate"
    )
    assert markdown == expected


def test_repo_signal_markdown_empty():
    signal = {"commits": [], "merged_prs": [], "opened_issues": []}

    assert rs.repo_signal_markdown(signal) == "No repo activity in this window."
