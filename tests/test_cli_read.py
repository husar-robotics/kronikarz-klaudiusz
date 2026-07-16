from __future__ import annotations

import json

import pytest

from klaudiusz import cli_read
from klaudiusz import config as config_module
from klaudiusz.cli import main
from klaudiusz.config import Config, DiscordConfig, ScheduleConfig, ShrekDogConfig
from klaudiusz.discord_api import DiscordClient, SearchNotIndexed

GUILD_ID = "g1"


def make_config() -> Config:
    return Config(
        discord=DiscordConfig(guild_id=GUILD_ID, newsletter_channel_id="c0", ignore_channels=()),
        shrek_dog=ShrekDogConfig(repo="husar-robotics/shrek-dog", log_dir="docs/research-log"),
        schedule=ScheduleConfig(timezone="Europe/Warsaw", quiet_day_message_threshold=10),
    )


class FakeClient:
    """Stands in for DiscordClient: no network, canned responses."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self) -> "FakeClient":
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False

    def guild_channels(self, guild_id):
        return [
            {"id": "c1", "name": "general", "type": DiscordClient.TEXT},
            {"id": "c2", "name": "papers", "type": DiscordClient.FORUM},
        ]

    def active_threads(self, guild_id):
        return [
            {
                "id": "500",
                "name": "live-chat",
                "parent_id": "c1",
                "type": DiscordClient.PUBLIC_THREAD,
            }
        ]

    def archived_public_threads(self, channel_id):
        return []

    def messages(self, channel_id, after=None, before=None):
        yield {
            "id": "1",
            "author": {"username": "bob", "global_name": None, "bot": False},
            "timestamp": "2026-07-11T10:00:00+00:00",
            "content": "hey",
            "attachments": [],
        }

    def search(self, guild_id, query, limit=25):
        return {
            "total_results": 1,
            "messages": [
                [
                    {
                        "id": "5",
                        "channel_id": "c1",
                        "author": {"username": "bob", "global_name": None},
                        "content": "hello world",
                    }
                ]
            ],
        }


class NotIndexedClient(FakeClient):
    def search(self, guild_id, query, limit=25):
        raise SearchNotIndexed(guild_id, "still indexing")


@pytest.fixture
def patch_client(monkeypatch):
    """Patch the DiscordClient class and config loading; no network or env needed."""

    def _apply(client_cls=FakeClient):
        monkeypatch.setattr(cli_read, "DiscordClient", client_cls)
        monkeypatch.setattr(config_module, "load_config", make_config)
        monkeypatch.setattr(config_module, "bot_token", lambda: "test-token")

    return _apply


# -- channels -------------------------------------------------------------------


def test_channels_lists_text_announcement_forum(patch_client, capsys):
    patch_client()

    exit_code = main(["channels"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "general" in out and "c1" in out and "text" in out
    assert "papers" in out and "c2" in out and "forum" in out


# -- pull -------------------------------------------------------------------


def test_pull_prints_markdown_transcript_by_default(patch_client, capsys):
    patch_client()

    exit_code = main(["pull", "--channel", "general", "--since", "3d"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "## #general" in out
    assert "bob" in out


def test_pull_json_prints_jsonl_records(patch_client, capsys):
    patch_client()

    exit_code = main(["pull", "--channel", "general", "--since", "3d", "--json"])

    out = capsys.readouterr().out
    assert exit_code == 0
    records = [json.loads(line) for line in out.splitlines() if line.strip()]
    assert records
    assert records[0]["channel_name"] == "general"
    assert records[0]["author"] == "bob"
    assert set(records[0]) == {
        "id",
        "channel_id",
        "channel_name",
        "thread_name",
        "author",
        "author_is_bot",
        "timestamp",
        "content",
        "attachment_urls",
        "jump_url",
    }


def test_pull_accepts_channel_by_id(patch_client, capsys):
    patch_client()

    exit_code = main(["pull", "--channel", "c1", "--since", "2026-07-01"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "## #general" in out


def test_pull_unknown_channel_exits(patch_client):
    patch_client()

    with pytest.raises(SystemExit):
        main(["pull", "--channel", "does-not-exist", "--since", "3d"])


def test_pull_bad_since_exits(patch_client):
    patch_client()

    with pytest.raises(SystemExit):
        main(["pull", "--channel", "general", "--since", "not-a-date"])


# -- search -----------------------------------------------------------------


def test_search_happy_path(patch_client, capsys):
    patch_client()

    exit_code = main(["search", "hello"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "bob" in out
    assert "channel c1" in out
    assert "hello world" in out


def test_search_not_indexed_explains_and_returns_nonzero(patch_client, capsys):
    patch_client(NotIndexedClient)

    exit_code = main(["search", "hello"])

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "index" in out.lower()


# -- thread -----------------------------------------------------------------


def test_thread_prints_transcript_with_resolved_names(patch_client, capsys):
    patch_client()

    exit_code = main(["thread", "500"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "## #general" in out
    assert "### thread: live-chat" in out
    assert "bob" in out


def test_thread_unknown_id_still_prints_messages(patch_client, capsys):
    patch_client()

    exit_code = main(["thread", "does-not-exist"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "## #unknown" in out
