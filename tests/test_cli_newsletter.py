from __future__ import annotations

import httpx
import pytest
import respx

from klaudiusz import config as config_module
from klaudiusz.cli import main
from klaudiusz.cli_newsletter import run
from klaudiusz.config import Config, DiscordConfig, ScheduleConfig, ShrekDogConfig

CHANNEL_ID = "c0"
DATE = "2026-07-11"


def make_config() -> Config:
    return Config(
        discord=DiscordConfig(guild_id="g1", newsletter_channel_id=CHANNEL_ID, ignore_channels=()),
        shrek_dog=ShrekDogConfig(repo="husar-robotics/shrek-dog", log_dir="docs/research-log"),
        schedule=ScheduleConfig(timezone="Europe/Warsaw", quiet_day_message_threshold=10),
    )


class FakeDiscordClient:
    """Records every call instead of touching the network."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self._next_id = 0

    def _new_id(self) -> str:
        self._next_id += 1
        return str(self._next_id)

    def post_message(self, channel_id, content=None, embeds=None):
        self.calls.append(("post_message", channel_id, content, embeds))
        return {"id": self._new_id()}

    def start_thread(self, channel_id, message_id, name):
        self.calls.append(("start_thread", channel_id, message_id, name))
        return {"id": f"thread-{message_id}"}


def _newsletter(**overrides: str) -> str:
    sections = {
        "TL;DR": "- point one\n- point two",
        "Discussions": "Some discussion. ([thread](https://discord.com/channels/1/2/3))",
        "Papers & links": (
            "- [Dead Paper](https://example.com/dead) is broken.\n"
            "- Check out https://example.com/dead-bare directly.\n"
            "- [Alive Paper](https://example.com/alive) is good."
        ),
        "Learning corner": "Some concept explained. See https://example.com/alive for more.",
    }
    sections.update(overrides)
    return "".join(f"## {title}\n{body}\n\n" for title, body in sections.items())


def _mock_links() -> None:
    respx.head("https://example.com/dead").mock(return_value=httpx.Response(404))
    respx.head("https://example.com/dead-bare").mock(return_value=httpx.Response(404))
    respx.head("https://example.com/alive").mock(return_value=httpx.Response(200))


# -- full post flow -----------------------------------------------------------


@respx.mock
def test_full_post_flow_order_and_payloads(tmp_path):
    _mock_links()
    cfg = make_config()
    client = FakeDiscordClient()

    result = run(
        _newsletter(),
        DATE,
        cfg,
        discord_client=client,
        dry_run=False,
        archive_dir=tmp_path,
    )

    assert len(client.calls) == 2 + len(result.rendered.embed_batches)

    lead_call = client.calls[0]
    assert lead_call[0] == "post_message"
    assert lead_call[1] == CHANNEL_ID
    assert lead_call[2] == result.rendered.lead
    assert lead_call[3] is None
    lead_message_id = result.lead_message_id
    assert lead_message_id is not None

    thread_call = client.calls[1]
    assert thread_call == ("start_thread", CHANNEL_ID, lead_message_id, f"TL;DR {DATE}")
    thread_id = result.thread_id
    assert thread_id == f"thread-{lead_message_id}"

    for batch, call in zip(result.rendered.embed_batches, client.calls[2:]):
        assert call[0] == "post_message"
        assert call[1] == thread_id
        assert call[2] is None
        assert call[3] == batch


# -- dead-link rewriting --------------------------------------------------------


@respx.mock
def test_dead_link_rewriting_and_drop_reporting(capsys, tmp_path):
    _mock_links()
    cfg = make_config()
    client = FakeDiscordClient()

    result = run(
        _newsletter(), DATE, cfg, discord_client=client, dry_run=False, archive_dir=tmp_path
    )

    # markdown link with a dead target: label kept, url gone
    assert "Dead Paper" in result.markdown
    assert "https://example.com/dead)" not in result.markdown
    assert "[Dead Paper]" not in result.markdown

    # bare dead url: wrapped in backticks
    assert "`https://example.com/dead-bare`" in result.markdown

    # live markdown link untouched
    assert "[Alive Paper](https://example.com/alive)" in result.markdown

    assert set(result.dropped_links) == {
        "https://example.com/dead",
        "https://example.com/dead-bare",
    }

    out = capsys.readouterr().out
    assert "https://example.com/dead" in out
    assert "https://example.com/dead-bare" in out


@respx.mock
def test_bare_dead_url_keeps_trailing_punctuation_outside_backticks():
    respx.head("https://example.com/dead2").mock(return_value=httpx.Response(404))
    cfg = make_config()
    markdown = _newsletter(**{"Learning corner": "Read https://example.com/dead2. Great stuff."})

    result = run(markdown, DATE, cfg, discord_client=None, dry_run=True)

    assert "`https://example.com/dead2`." in result.markdown


# -- discord.com exemption -----------------------------------------------------


@respx.mock
def test_discord_urls_are_never_validated():
    discord_route = respx.head("https://discord.com/channels/1/2/3").mock(
        return_value=httpx.Response(200)
    )
    _mock_links()
    cfg = make_config()

    run(_newsletter(), DATE, cfg, discord_client=None, dry_run=True)

    assert not discord_route.called


# -- archive ---------------------------------------------------------------------


@respx.mock
def test_archive_written_on_real_run(tmp_path):
    _mock_links()
    cfg = make_config()
    client = FakeDiscordClient()

    result = run(
        _newsletter(), DATE, cfg, discord_client=client, dry_run=False, archive_dir=tmp_path
    )

    archive_file = tmp_path / f"{DATE}.md"
    assert archive_file.is_file()
    assert archive_file.read_text() == result.markdown
    assert result.archive_path == archive_file


@respx.mock
def test_dry_run_writes_no_archive_and_makes_no_discord_calls(tmp_path):
    _mock_links()
    cfg = make_config()
    client = FakeDiscordClient()

    result = run(
        _newsletter(), DATE, cfg, discord_client=client, dry_run=True, archive_dir=tmp_path
    )

    assert client.calls == []
    assert result.archive_path is None
    assert result.lead_message_id is None
    assert result.thread_id is None
    assert list(tmp_path.iterdir()) == []


# -- section validation propagates ------------------------------------------------


@respx.mock
def test_missing_section_propagates_render_loud_failure():
    cfg = make_config()
    client = FakeDiscordClient()
    incomplete = "## TL;DR\n- point one\n\n## Discussions\nnothing much\n"

    with pytest.raises(SystemExit):
        run(incomplete, DATE, cfg, discord_client=client, dry_run=False)

    assert client.calls == []


# -- CLI registration -------------------------------------------------------------


def test_post_newsletter_registered_in_cli():
    with pytest.raises(SystemExit) as exc_info:
        main(["post-newsletter", "--help"])
    assert exc_info.value.code == 0


@respx.mock
def test_cli_dry_run_end_to_end(monkeypatch, tmp_path, capsys):
    """`klaudiusz post-newsletter <file> --date ... --dry-run` through main(); no Discord client."""
    _mock_links()
    monkeypatch.setattr(config_module, "load_config", make_config)
    newsletter_file = tmp_path / "newsletter.md"
    newsletter_file.write_text(_newsletter())

    exit_code = main(["post-newsletter", str(newsletter_file), "--date", DATE, "--dry-run"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "[DRY RUN] lead:" in out
    assert "[DRY RUN] embed batches:" in out
    assert "[DROP] dead link removed: https://example.com/dead" in out


def test_cli_missing_file_fails_loudly(monkeypatch, tmp_path):
    monkeypatch.setattr(config_module, "load_config", make_config)

    with pytest.raises(SystemExit):
        main(["post-newsletter", str(tmp_path / "nope.md"), "--date", DATE, "--dry-run"])


def test_post_requires_writer_token_loudly_and_precedes_client(monkeypatch, tmp_path):
    """A reader token must not satisfy post-newsletter, and the failure must
    come before a Discord client is ever constructed."""
    from klaudiusz import cli_newsletter

    monkeypatch.setattr(config_module, "load_config", make_config)
    monkeypatch.setenv("DISCORD_READER_TOKEN", "reader-tok")

    class ExplodingClient:
        def __init__(self, *args, **kwargs):
            pytest.fail("DiscordClient must not be constructed without a writer token")

    monkeypatch.setattr(cli_newsletter, "DiscordClient", ExplodingClient)
    newsletter_file = tmp_path / "newsletter.md"
    newsletter_file.write_text(_newsletter())

    with pytest.raises(SystemExit) as excinfo:
        main(["post-newsletter", str(newsletter_file), "--date", DATE])

    assert "auth --writer" in str(excinfo.value)
