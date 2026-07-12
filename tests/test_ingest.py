from __future__ import annotations

from datetime import date, datetime, timezone

import httpx
import respx

from klaudiusz.config import Config, DiscordConfig, ScheduleConfig, ShrekDogConfig
from klaudiusz.discord_api import API_BASE_URL, DiscordClient
from klaudiusz.ingest import (
    day_window,
    display_name,
    normalize_message,
    pull_channel,
    pull_window,
    transcript_markdown,
    window_snowflakes,
)

GUILD_ID = "g1"
WINDOW_START = datetime(2026, 7, 11, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 7, 12, tzinfo=timezone.utc)
AFTER, BEFORE = window_snowflakes(WINDOW_START, WINDOW_END)
AFTER_INT, BEFORE_INT = int(AFTER), int(BEFORE)

CH_GENERAL = "c1"
CH_BOT_NEWS = "c2"  # in ignore_channels
CH_PAPERS = "c3"  # forum

ACTIVE_THREAD = str(AFTER_INT + 500)  # in-window, parented to c1 -> pulled
TOO_NEW_THREAD = str(BEFORE_INT + 100)  # created after window end -> skipped
IGNORED_PARENT_THREAD = str(AFTER_INT + 700)  # parented to the ignored channel -> skipped
PRIVATE_THREAD_ID = str(AFTER_INT + 800)  # private, not public -> skipped

ARCHIVED_FRESH_THREAD = str(AFTER_INT + 600)  # last_message_id inside window -> pulled
ARCHIVED_STALE_THREAD = str(AFTER_INT + 10)  # last_message_id before window start -> skipped


def make_config(ignore_channels=("bot-news",)):
    return Config(
        discord=DiscordConfig(
            guild_id=GUILD_ID, newsletter_channel_id="c0", ignore_channels=ignore_channels
        ),
        shrek_dog=ShrekDogConfig(repo="husar-robotics/shrek-dog", log_dir="docs/research-log"),
        schedule=ScheduleConfig(timezone="Europe/Warsaw", quiet_day_message_threshold=10),
    )


def discord_message(
    msg_id,
    *,
    author="alice",
    global_name=None,
    bot=False,
    content="hi",
    timestamp="2026-07-11T09:00:00+00:00",
    attachments=None,
):
    return {
        "id": msg_id,
        "author": {"username": author, "global_name": global_name, "bot": bot},
        "timestamp": timestamp,
        "content": content,
        "attachments": attachments or [],
    }


def _register_fixture_guild() -> dict[str, respx.Route]:
    """A guild with 2 text channels (one ignored), 1 forum, and a handful of threads.

    Registers only the routes a correct `pull_window` should ever hit; any
    other request (e.g. messages for a skipped thread, or bot-news at all)
    fails the test via respx's unmocked-request error.
    """
    routes: dict[str, respx.Route] = {}

    routes["channels"] = respx.get(f"{API_BASE_URL}/guilds/{GUILD_ID}/channels").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"id": CH_GENERAL, "name": "general", "type": DiscordClient.TEXT},
                {"id": CH_BOT_NEWS, "name": "bot-news", "type": DiscordClient.TEXT},
                {"id": CH_PAPERS, "name": "papers", "type": DiscordClient.FORUM},
            ],
        )
    )
    routes["active_threads"] = respx.get(f"{API_BASE_URL}/guilds/{GUILD_ID}/threads/active").mock(
        return_value=httpx.Response(
            200,
            json={
                "threads": [
                    {
                        "id": ACTIVE_THREAD,
                        "name": "live-chat",
                        "parent_id": CH_GENERAL,
                        "type": DiscordClient.PUBLIC_THREAD,
                    },
                    {
                        "id": TOO_NEW_THREAD,
                        "name": "too-new",
                        "parent_id": CH_GENERAL,
                        "type": DiscordClient.PUBLIC_THREAD,
                    },
                    {
                        "id": IGNORED_PARENT_THREAD,
                        "name": "ignored-parent",
                        "parent_id": CH_BOT_NEWS,
                        "type": DiscordClient.PUBLIC_THREAD,
                    },
                    {
                        "id": PRIVATE_THREAD_ID,
                        "name": "private-chat",
                        "parent_id": CH_GENERAL,
                        "type": DiscordClient.PRIVATE_THREAD,
                    },
                ],
                "members": [],
            },
        )
    )
    routes["archived_general"] = respx.get(
        f"{API_BASE_URL}/channels/{CH_GENERAL}/threads/archived/public"
    ).mock(return_value=httpx.Response(200, json={"threads": [], "members": [], "has_more": False}))
    routes["archived_papers"] = respx.get(
        f"{API_BASE_URL}/channels/{CH_PAPERS}/threads/archived/public"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "threads": [
                    {
                        "id": ARCHIVED_FRESH_THREAD,
                        "name": "paper-alpha",
                        "parent_id": CH_PAPERS,
                        "last_message_id": str(AFTER_INT + 650),
                    },
                    {
                        "id": ARCHIVED_STALE_THREAD,
                        "name": "paper-stale",
                        "parent_id": CH_PAPERS,
                        "last_message_id": str(AFTER_INT - 100),
                    },
                ],
                "members": [],
                "has_more": False,
            },
        )
    )

    routes["general_messages"] = respx.get(f"{API_BASE_URL}/channels/{CH_GENERAL}/messages").mock(
        return_value=httpx.Response(
            200,
            json=[
                discord_message(
                    str(AFTER_INT + 200),
                    author="bot-account",
                    bot=True,
                    content="daily digest",
                    timestamp="2026-07-11T09:05:00+00:00",
                ),
                discord_message(
                    str(AFTER_INT + 100),
                    author="alice",
                    global_name="Alice A.",
                    content="morning\nsecond line",
                    attachments=[{"url": "https://cdn.example.com/f.png"}],
                    timestamp="2026-07-11T09:00:00+00:00",
                ),
            ],  # newest first, like the real API
        )
    )
    routes["active_thread_messages"] = respx.get(f"{API_BASE_URL}/channels/{ACTIVE_THREAD}/messages").mock(
        return_value=httpx.Response(200, json=[discord_message(str(AFTER_INT + 550))])
    )
    routes["archived_fresh_messages"] = respx.get(
        f"{API_BASE_URL}/channels/{ARCHIVED_FRESH_THREAD}/messages"
    ).mock(return_value=httpx.Response(200, json=[discord_message(str(AFTER_INT + 640))]))

    return routes


def _client() -> DiscordClient:
    return DiscordClient("test-token")


# -- snowflake math -----------------------------------------------------------


def test_window_snowflakes_matches_known_timestamp():
    # 2026-07-11T00:00:00+02:00 == 2026-07-10T22:00:00Z; verified independently
    # against the formula snowflake = (unix_ms - 1420070400000) << 22. `after`
    # is one below the start snowflake because Discord's `after` is exclusive.
    start = datetime.fromisoformat("2026-07-11T00:00:00+02:00")
    end = datetime.fromisoformat("2026-07-12T00:00:00+02:00")

    after, before = window_snowflakes(start, end)

    assert after == "1525260327321599999"
    assert before == "1525622715187200000"


def test_day_window_is_local_midnight_to_midnight():
    start, end = day_window(date(2026, 7, 11), "Europe/Warsaw")

    assert start.isoformat() == "2026-07-11T00:00:00+02:00"
    assert end.isoformat() == "2026-07-12T00:00:00+02:00"


# -- normalize_message / display_name -----------------------------------------


def test_display_name_prefers_global_name():
    assert display_name({"username": "alice", "global_name": "Alice A."}) == "Alice A."


def test_display_name_falls_back_to_username():
    assert display_name({"username": "alice", "global_name": None}) == "alice"


def test_normalize_message_has_every_contract_key():
    msg = discord_message("42", global_name="Alice A.", attachments=[{"url": "https://x/y.png"}])
    record = normalize_message(
        msg, channel_id="c1", channel_name="general", thread_name=None, guild_id=GUILD_ID
    )

    assert set(record) == {
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
    assert record["id"] == "42"
    assert record["author"] == "Alice A."
    assert record["author_is_bot"] is False
    assert record["attachment_urls"] == ["https://x/y.png"]
    assert record["jump_url"] == f"https://discord.com/channels/{GUILD_ID}/c1/42"


def test_normalize_message_thread_jump_url_uses_thread_id_as_channel():
    msg = discord_message("99")
    record = normalize_message(
        msg, channel_id="t1", channel_name="papers", thread_name="paper-alpha", guild_id=GUILD_ID
    )

    assert record["channel_id"] == "t1"
    assert record["thread_name"] == "paper-alpha"
    assert record["jump_url"] == f"https://discord.com/channels/{GUILD_ID}/t1/99"


# -- pull_window: enumeration and window filtering -----------------------------


@respx.mock
def test_pull_window_enumerates_channels_and_threads_correctly():
    routes = _register_fixture_guild()
    config = make_config()

    with _client() as client:
        records = pull_window(client, config, WINDOW_START, WINDOW_END)

    ids = {r["id"] for r in records}
    assert ids == {
        str(AFTER_INT + 200),
        str(AFTER_INT + 100),
        str(AFTER_INT + 550),
        str(AFTER_INT + 640),
    }
    # bot-news is ignored: neither its own messages nor any endpoint scoped to
    # it (archived threads) should ever be requested.
    assert routes["archived_general"].called
    assert routes["archived_papers"].called
    assert f"{API_BASE_URL}/channels/{CH_BOT_NEWS}" not in "".join(
        str(c.request.url) for c in respx.calls
    )


@respx.mock
def test_pull_window_skips_channels_the_bot_cannot_read(capsys):
    # The guild channel list includes channels whose overwrites deny the bot
    # access (verified live 2026-07-12); their /messages returns 403 code
    # 50001 and must be skipped, not kill the pull.
    routes = _register_fixture_guild()
    config = make_config()
    routes["general_messages"].mock(
        return_value=httpx.Response(403, json={"message": "Missing Access", "code": 50001})
    )

    with _client() as client:
        records = pull_window(client, config, WINDOW_START, WINDOW_END)

    ids = {r["id"] for r in records}
    assert ids == {str(AFTER_INT + 550), str(AFTER_INT + 640)}
    assert "skipping #general" in capsys.readouterr().err


@respx.mock
def test_pull_window_sends_window_bounds_to_messages_endpoint():
    _register_fixture_guild()
    config = make_config()

    with _client() as client:
        pull_window(client, config, WINDOW_START, WINDOW_END)

    general_call = respx.get(f"{API_BASE_URL}/channels/{CH_GENERAL}/messages").calls.last
    assert general_call.request.url.params["after"] == AFTER
    assert general_call.request.url.params["limit"] == "100"


@respx.mock
def test_pull_window_record_shape_and_thread_fields():
    _register_fixture_guild()
    config = make_config()

    with _client() as client:
        records = pull_window(client, config, WINDOW_START, WINDOW_END)

    by_id = {r["id"]: r for r in records}

    plain = by_id[str(AFTER_INT + 100)]
    assert plain["channel_id"] == CH_GENERAL
    assert plain["channel_name"] == "general"
    assert plain["thread_name"] is None
    assert plain["author"] == "Alice A."
    assert plain["author_is_bot"] is False
    assert plain["attachment_urls"] == ["https://cdn.example.com/f.png"]
    assert plain["jump_url"] == f"https://discord.com/channels/{GUILD_ID}/{CH_GENERAL}/{plain['id']}"

    bot_msg = by_id[str(AFTER_INT + 200)]
    assert bot_msg["author_is_bot"] is True

    thread_msg = by_id[str(AFTER_INT + 550)]
    assert thread_msg["channel_id"] == ACTIVE_THREAD
    assert thread_msg["channel_name"] == "general"
    assert thread_msg["thread_name"] == "live-chat"
    assert thread_msg["jump_url"] == f"https://discord.com/channels/{GUILD_ID}/{ACTIVE_THREAD}/{thread_msg['id']}"

    forum_thread_msg = by_id[str(AFTER_INT + 640)]
    assert forum_thread_msg["channel_id"] == ARCHIVED_FRESH_THREAD
    assert forum_thread_msg["channel_name"] == "papers"
    assert forum_thread_msg["thread_name"] == "paper-alpha"


@respx.mock
def test_pull_window_sorts_chronologically_by_id():
    _register_fixture_guild()
    config = make_config()

    with _client() as client:
        records = pull_window(client, config, WINDOW_START, WINDOW_END)

    ids = [int(r["id"]) for r in records]
    assert ids == sorted(ids)


@respx.mock
def test_pull_channel_scopes_to_one_channel_and_its_threads():
    _register_fixture_guild()
    config = make_config()
    channel = {"id": CH_GENERAL, "name": "general", "type": DiscordClient.TEXT}

    with _client() as client:
        records = pull_channel(client, config, channel, WINDOW_START, WINDOW_END)

    ids = {r["id"] for r in records}
    assert ids == {str(AFTER_INT + 200), str(AFTER_INT + 100), str(AFTER_INT + 550)}
    assert all(r["channel_name"] == "general" for r in records)


# -- transcript_markdown -------------------------------------------------------


def test_transcript_markdown_empty():
    assert transcript_markdown([]) == "No messages in this window.\n"


def test_transcript_markdown_groups_plain_before_threads_chronologically():
    records = [
        normalize_message(
            discord_message("1", timestamp="2026-07-11T09:00:00+00:00"),
            channel_id="c1",
            channel_name="general",
            thread_name=None,
            guild_id=GUILD_ID,
        ),
        normalize_message(
            discord_message("2", timestamp="2026-07-11T09:05:00+00:00"),
            channel_id="t1",
            channel_name="general",
            thread_name="live-chat",
            guild_id=GUILD_ID,
        ),
        normalize_message(
            discord_message("3", timestamp="2026-07-11T09:10:00+00:00"),
            channel_id="t2",
            channel_name="papers",
            thread_name="paper-alpha",
            guild_id=GUILD_ID,
        ),
    ]

    md = transcript_markdown(records)

    assert md.index("## #general") < md.index("### thread: live-chat")
    assert md.index("### thread: live-chat") < md.index("## #papers")
    assert md.index("## #papers") < md.index("### thread: paper-alpha")


def test_transcript_markdown_bot_marker_and_time_and_jump_url():
    record = normalize_message(
        discord_message("1", author="klaudiusz", bot=True, content="hi", timestamp="2026-07-11T14:30:00+00:00"),
        channel_id="c1",
        channel_name="general",
        thread_name=None,
        guild_id=GUILD_ID,
    )

    md = transcript_markdown([record])

    assert "**klaudiusz** [bot] (14:30) hi" in md
    assert f"[↗](https://discord.com/channels/{GUILD_ID}/c1/1)" in md


def test_transcript_markdown_indents_multiline_content():
    record = normalize_message(
        discord_message("1", content="line one\nline two", timestamp="2026-07-11T09:00:00+00:00"),
        channel_id="c1",
        channel_name="general",
        thread_name=None,
        guild_id=GUILD_ID,
    )

    md = transcript_markdown([record])

    assert "line one" in md
    assert "\n  line two" in md
