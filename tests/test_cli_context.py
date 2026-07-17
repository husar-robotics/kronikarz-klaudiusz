from __future__ import annotations

import json

import httpx
import pytest
import respx

from klaudiusz import cli_context
from klaudiusz import config as config_module
from klaudiusz.cli import main
from klaudiusz.config import Config, DiscordConfig, ScheduleConfig, ShrekDogConfig
from klaudiusz.discord_api import DiscordClient

GUILD_ID = "g1"
REPO = "husar-robotics/shrek-dog"

ARXIV_ATOM_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2406.01234v2</id>
    <title>Attention Is What You Need</title>
    <author><name>Jane Doe</name></author>
  </entry>
</feed>
"""


def make_config(threshold: int = 10) -> Config:
    return Config(
        discord=DiscordConfig(guild_id=GUILD_ID, newsletter_channel_id="c0", ignore_channels=()),
        shrek_dog=ShrekDogConfig(repo=REPO, log_dir="docs/research-log"),
        schedule=ScheduleConfig(timezone="Europe/Warsaw", quiet_day_message_threshold=threshold),
    )


def _discord_msg(msg_id: str, author: str, content: str, attachments=None) -> dict:
    return {
        "id": msg_id,
        "author": {"username": author, "global_name": None, "bot": False},
        "timestamp": "2026-07-11T10:00:00+00:00",
        "content": content,
        "attachments": attachments or [],
    }


def make_client(messages: list[dict]):
    class FakeClient:
        """Stands in for DiscordClient: one text channel, no threads, canned messages."""

        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *exc_info: object) -> bool:
            return False

        def guild_channels(self, guild_id):
            return [{"id": "c1", "name": "general", "type": DiscordClient.TEXT}]

        def active_threads(self, guild_id):
            return []

        def archived_public_threads(self, channel_id):
            return []

        def messages(self, channel_id, after=None, before=None):
            yield from messages

    return FakeClient


QUIET_MESSAGES = [_discord_msg(str(100 + i), f"user{i}", f"hello {i}") for i in range(3)]

BUSY_MESSAGES = [_discord_msg(str(200 + i), f"user{i}", f"discussing thing {i}") for i in range(11)]
BUSY_MESSAGES.append(
    _discord_msg(
        "999",
        "alice",
        "found this paper https://arxiv.org/abs/2406.01234 worth a read",
    )
)


def _empty_signal() -> dict:
    return {"commits": [], "merged_prs": [], "opened_issues": []}


@pytest.fixture
def patch_env(monkeypatch):
    def _apply(messages: list[dict], threshold: int = 10, signal: dict | None = None):
        fixed_signal = signal if signal is not None else _empty_signal()
        monkeypatch.setattr(cli_context, "DiscordClient", make_client(messages))
        monkeypatch.setattr(config_module, "load_config", lambda: make_config(threshold))
        monkeypatch.setattr(config_module, "bot_token", lambda: "test-token")
        monkeypatch.setattr(cli_context, "repo_signal", lambda repo, start, end: fixed_signal)

    return _apply


def test_quiet_day_writes_bundle_and_exits_2(patch_env, tmp_path, capsys):
    patch_env(QUIET_MESSAGES, threshold=10)
    out_dir = tmp_path / "bundle"

    exit_code = main(["context", "--date", "2026-07-11", "--out", str(out_dir)])

    out = capsys.readouterr().out
    assert exit_code == 2
    assert "QUIET DAY" in out

    meta = json.loads((out_dir / "meta.json").read_text())
    assert meta == {
        "date": "2026-07-11",
        "message_count": 3,
        "channel_count": 1,
        "repo_event_count": 0,
        "quiet": True,
    }
    assert (out_dir / "transcript.md").exists()
    assert (out_dir / "repo-signal.md").exists()
    assert (out_dir / "links.md").exists()


@respx.mock
def test_busy_day_exits_0_and_resolves_arxiv_link(patch_env, tmp_path, capsys):
    respx.get("https://export.arxiv.org/api/query", params={"id_list": "2406.01234"}).mock(
        return_value=httpx.Response(200, text=ARXIV_ATOM_FIXTURE)
    )
    patch_env(BUSY_MESSAGES, threshold=10)
    out_dir = tmp_path / "bundle"

    exit_code = main(["context", "--date", "2026-07-11", "--out", str(out_dir)])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "QUIET DAY" not in out

    meta = json.loads((out_dir / "meta.json").read_text())
    assert meta["message_count"] == 12
    assert meta["channel_count"] == 1
    assert meta["repo_event_count"] == 0
    assert meta["quiet"] is False

    transcript = (out_dir / "transcript.md").read_text()
    assert "## #general" in transcript
    assert "alice" in transcript

    links_md = (out_dir / "links.md").read_text()
    assert "Attention Is What You Need" in links_md
    assert "Jane Doe" in links_md
    assert "arxiv" in links_md

    repo_signal_md = (out_dir / "repo-signal.md").read_text()
    assert repo_signal_md == "No repo activity in this window."


def test_busy_day_from_repo_events_alone(patch_env, tmp_path):
    signal = _empty_signal()
    signal["commits"] = [
        {
            "sha": "aaaaaaa",
            "author": "ada",
            "message": "Fix thing",
            "url": f"https://github.com/{REPO}/commit/{'a' * 40}",
        }
    ]
    patch_env(QUIET_MESSAGES, threshold=10, signal=signal)
    out_dir = tmp_path / "bundle"

    exit_code = main(["context", "--date", "2026-07-11", "--out", str(out_dir)])

    assert exit_code == 0
    meta = json.loads((out_dir / "meta.json").read_text())
    assert meta["repo_event_count"] == 1
    assert meta["quiet"] is False

    repo_signal_md = (out_dir / "repo-signal.md").read_text()
    assert "## Commits" in repo_signal_md
    assert "[aaaaaaa]" in repo_signal_md
    assert "Fix thing — ada" in repo_signal_md


def test_refuses_non_empty_existing_out_dir(patch_env, tmp_path):
    patch_env(QUIET_MESSAGES)
    out_dir = tmp_path / "bundle"
    out_dir.mkdir()
    (out_dir / "stray.txt").write_text("leftover")

    with pytest.raises(SystemExit):
        main(["context", "--date", "2026-07-11", "--out", str(out_dir)])


def test_accepts_empty_existing_out_dir(patch_env, tmp_path):
    patch_env(QUIET_MESSAGES)
    out_dir = tmp_path / "bundle"
    out_dir.mkdir()

    exit_code = main(["context", "--date", "2026-07-11", "--out", str(out_dir)])

    assert exit_code == 2  # quiet fixture
    assert (out_dir / "meta.json").exists()


def test_bad_date_exits_loudly(patch_env, tmp_path):
    patch_env(QUIET_MESSAGES)

    with pytest.raises(SystemExit):
        main(["context", "--date", "not-a-date", "--out", str(tmp_path / "bundle")])


def test_default_out_dir_is_context_dash_date(patch_env, tmp_path, monkeypatch):
    patch_env(QUIET_MESSAGES)
    monkeypatch.chdir(tmp_path)

    exit_code = main(["context", "--date", "2026-07-11"])

    assert exit_code == 2
    assert (tmp_path / "context-2026-07-11" / "meta.json").exists()
