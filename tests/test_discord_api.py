from __future__ import annotations

import json

import httpx
import pytest
import respx

from klaudiusz.discord_api import (
    API_BASE_URL,
    DiscordAPIError,
    DiscordClient,
    SearchNotIndexed,
)


def _client(sleeps: list[float] | None = None) -> DiscordClient:
    recorded = sleeps if sleeps is not None else []
    return DiscordClient("test-token", sleep=recorded.append)


def _page(start: int, count: int) -> list[dict]:
    """Build a Discord-shaped page: ids [start, start+count), newest-first."""
    return [{"id": str(i), "content": f"m{i}"} for i in range(start + count - 1, start - 1, -1)]


# -- construction -----------------------------------------------------------


def test_client_sets_auth_header_and_user_agent():
    client = DiscordClient("abc123")
    try:
        assert client._client.headers["authorization"] == "Bot abc123"
        assert "kronikarz-klaudiusz" in client._client.headers["user-agent"]
        assert str(client._client.base_url) == API_BASE_URL + "/"
    finally:
        client.close()


def test_context_manager_closes_client():
    with DiscordClient("abc123") as client:
        assert not client._client.is_closed
    assert client._client.is_closed


# -- channels & threads -------------------------------------------------------


@respx.mock
def test_guild_channels_returns_list():
    respx.get(f"{API_BASE_URL}/guilds/g1/channels").mock(
        return_value=httpx.Response(200, json=[{"id": "1", "type": 0}])
    )
    with _client() as client:
        assert client.guild_channels("g1") == [{"id": "1", "type": 0}]


@respx.mock
def test_active_threads_unwraps_threads_key():
    respx.get(f"{API_BASE_URL}/guilds/g1/threads/active").mock(
        return_value=httpx.Response(200, json={"threads": [{"id": "t1"}], "members": []})
    )
    with _client() as client:
        assert client.active_threads("g1") == [{"id": "t1"}]


@respx.mock
def test_archived_public_threads_unwraps_threads_key():
    respx.get(f"{API_BASE_URL}/channels/c1/threads/archived/public").mock(
        return_value=httpx.Response(
            200, json={"threads": [{"id": "t2"}], "members": [], "has_more": False}
        )
    )
    with _client() as client:
        assert client.archived_public_threads("c1") == [{"id": "t2"}]


# -- messages pagination ------------------------------------------------------


@respx.mock
def test_messages_paginates_three_pages_every_message_once_in_order():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        after = request.url.params.get("after")
        calls.append(after)
        assert request.url.params.get("limit") == "100"
        if after == "0":
            return httpx.Response(200, json=_page(1, 100))
        if after == "100":
            return httpx.Response(200, json=_page(101, 100))
        if after == "200":
            return httpx.Response(200, json=_page(201, 50))
        raise AssertionError(f"unexpected after={after!r}")

    respx.get(f"{API_BASE_URL}/channels/chan1/messages").mock(side_effect=handler)

    with _client() as client:
        result = list(client.messages("chan1"))

    assert [m["id"] for m in result] == [str(i) for i in range(1, 251)]
    # the last page was short (50 < limit 100), so pagination stops without
    # an extra request to confirm exhaustion
    assert calls == ["0", "100", "200"]


@respx.mock
def test_messages_starts_from_explicit_after_cursor():
    respx.get(f"{API_BASE_URL}/channels/chan1/messages").mock(
        side_effect=[
            httpx.Response(200, json=_page(500, 10)),
            httpx.Response(200, json=[]),
        ]
    )
    with _client() as client:
        result = list(client.messages("chan1", after="499"))

    assert [m["id"] for m in result] == [str(i) for i in range(500, 510)]


@respx.mock
def test_messages_stops_at_before_boundary_without_extra_request():
    """`before` is enforced client-side; once exceeded, no further page is fetched."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.params.get("after"))
        return httpx.Response(200, json=_page(1, 100))

    respx.get(f"{API_BASE_URL}/channels/chan1/messages").mock(side_effect=handler)

    with _client() as client:
        result = list(client.messages("chan1", before="50"))

    assert [m["id"] for m in result] == [str(i) for i in range(1, 50)]
    assert calls == ["0"]


@respx.mock
def test_messages_empty_channel_yields_nothing():
    respx.get(f"{API_BASE_URL}/channels/chan1/messages").mock(
        return_value=httpx.Response(200, json=[])
    )
    with _client() as client:
        assert list(client.messages("chan1")) == []


# -- rate limiting ----------------------------------------------------------


@respx.mock
def test_429_response_sleeps_retry_after_and_retries_once():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(429, json={"message": "rate limited", "retry_after": 1.5})
        return httpx.Response(200, json=[{"id": "1"}])

    respx.get(f"{API_BASE_URL}/guilds/g1/channels").mock(side_effect=handler)

    sleeps: list[float] = []
    with _client(sleeps) as client:
        result = client.guild_channels("g1")

    assert result == [{"id": "1"}]
    assert sleeps == [1.5]
    assert attempts["n"] == 2


@respx.mock
def test_429_twice_raises_after_single_retry():
    respx.get(f"{API_BASE_URL}/guilds/g1/channels").mock(
        return_value=httpx.Response(429, json={"message": "rate limited", "retry_after": 0.1})
    )
    sleeps: list[float] = []
    with _client(sleeps) as client:
        with pytest.raises(DiscordAPIError):
            client.guild_channels("g1")

    # exactly one retry: one sleep call, regardless of the repeated 429
    assert sleeps == [0.1]


@respx.mock
def test_rate_limit_remaining_zero_sleeps_reset_after():
    respx.get(f"{API_BASE_URL}/guilds/g1/channels").mock(
        return_value=httpx.Response(
            200,
            json=[],
            headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset-After": "3.25"},
        )
    )
    sleeps: list[float] = []
    with _client(sleeps) as client:
        client.guild_channels("g1")

    assert sleeps == [3.25]


@respx.mock
def test_rate_limit_remaining_nonzero_does_not_sleep():
    respx.get(f"{API_BASE_URL}/guilds/g1/channels").mock(
        return_value=httpx.Response(
            200,
            json=[],
            headers={"X-RateLimit-Remaining": "5", "X-RateLimit-Reset-After": "3.25"},
        )
    )
    sleeps: list[float] = []
    with _client(sleeps) as client:
        client.guild_channels("g1")

    assert sleeps == []


# -- errors -------------------------------------------------------------------


@respx.mock
def test_generic_error_raises_with_method_url_status_body():
    respx.get(f"{API_BASE_URL}/guilds/g1/channels").mock(
        return_value=httpx.Response(403, text="missing access")
    )
    with _client() as client:
        with pytest.raises(DiscordAPIError) as excinfo:
            client.guild_channels("g1")

    message = str(excinfo.value)
    assert "GET" in message
    assert "/guilds/g1/channels" in message
    assert "403" in message
    assert "missing access" in message


@respx.mock
def test_search_not_indexed_raises_typed_exception():
    respx.get(f"{API_BASE_URL}/guilds/g1/messages/search").mock(
        return_value=httpx.Response(
            403,
            json={"message": "This guild is still being indexed.", "code": 110000},
        )
    )
    with _client() as client:
        with pytest.raises(SearchNotIndexed) as excinfo:
            client.search("g1", "torque", limit=10)

    assert excinfo.value.guild_id == "g1"


@respx.mock
def test_search_other_error_raises_generic():
    respx.get(f"{API_BASE_URL}/guilds/g1/messages/search").mock(
        return_value=httpx.Response(500, text="internal error")
    )
    with _client() as client:
        with pytest.raises(DiscordAPIError):
            client.search("g1", "torque")


@respx.mock
def test_search_success_returns_json():
    respx.get(f"{API_BASE_URL}/guilds/g1/messages/search").mock(
        return_value=httpx.Response(200, json={"total_results": 1, "messages": [[{"id": "1"}]]})
    )
    with _client() as client:
        result = client.search("g1", "torque")

    assert result["total_results"] == 1


# -- write helpers inject allowed_mentions -------------------------------------


@respx.mock
def test_post_message_injects_allowed_mentions():
    route = respx.post(f"{API_BASE_URL}/channels/c1/messages").mock(
        return_value=httpx.Response(200, json={"id": "m1"})
    )
    with _client() as client:
        client.post_message("c1", content="hello")

    sent = json.loads(route.calls.last.request.content)
    assert sent["allowed_mentions"] == {"parse": []}
    assert sent["content"] == "hello"


@respx.mock
def test_post_message_with_embeds_injects_allowed_mentions():
    route = respx.post(f"{API_BASE_URL}/channels/c1/messages").mock(
        return_value=httpx.Response(200, json={"id": "m1"})
    )
    with _client() as client:
        client.post_message("c1", embeds=[{"title": "t"}])

    sent = json.loads(route.calls.last.request.content)
    assert sent["allowed_mentions"] == {"parse": []}
    assert sent["embeds"] == [{"title": "t"}]
    assert "content" not in sent


@respx.mock
def test_start_thread_injects_allowed_mentions():
    route = respx.post(f"{API_BASE_URL}/channels/c1/messages/m1/threads").mock(
        return_value=httpx.Response(200, json={"id": "t1", "name": "TL;DR 2026-07-11"})
    )
    with _client() as client:
        client.start_thread("c1", "m1", "TL;DR 2026-07-11")

    sent = json.loads(route.calls.last.request.content)
    assert sent["allowed_mentions"] == {"parse": []}
    assert sent["name"] == "TL;DR 2026-07-11"
