"""REST client for the Discord bot API: channels, threads, messages, search, posting."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator

import httpx

API_BASE_URL = "https://discord.com/api/v10"
USER_AGENT = "DiscordBot (https://github.com/husar-robotics/kronikarz-klaudiusz, 0.1.0)"

SEARCH_NOT_INDEXED_CODE = 110000

_PAGE_LIMIT = 100


class DiscordAPIError(RuntimeError):
    """A non-2xx Discord response not otherwise handled.

    Carries the method, URL, status, and response body: the API's own error
    body is far more useful than a bare status code.
    """

    def __init__(self, resp: httpx.Response) -> None:
        super().__init__(
            f"{resp.request.method} {resp.request.url} -> {resp.status_code}\n{resp.text}"
        )
        self.response = resp
        self.status_code = resp.status_code


class SearchNotIndexed(RuntimeError):
    """Discord error code 110000: the guild hasn't finished indexing for search yet."""

    def __init__(self, guild_id: str, message: str) -> None:
        super().__init__(f"guild {guild_id} is not indexed for search yet: {message}")
        self.guild_id = guild_id


def _safe_json(resp: httpx.Response) -> dict:
    try:
        body = resp.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _retry_after_seconds(resp: httpx.Response) -> float:
    body = _safe_json(resp)
    if "retry_after" in body:
        return float(body["retry_after"])
    header = resp.headers.get("Retry-After")
    return float(header) if header is not None else 1.0


class DiscordClient:
    """Thin wrapper over httpx.Client for the Discord bot REST API.

    Handles auth, the shared rate-limit rules, and loud failures. Nothing in
    here hardcodes a per-route limit; every route is throttled the same way
    from the response headers Discord sends back.
    """

    # Channel types this project cares about (Discord's full enum is larger).
    TEXT = 0
    ANNOUNCEMENT = 5
    PUBLIC_THREAD = 11
    PRIVATE_THREAD = 12
    FORUM = 15

    def __init__(
        self,
        token: str,
        *,
        sleep: Callable[[float], None] = time.sleep,
        timeout: float = 30.0,
    ) -> None:
        self._sleep = sleep
        self._client = httpx.Client(
            base_url=API_BASE_URL,
            headers={"Authorization": f"Bot {token}", "User-Agent": USER_AGENT},
            timeout=timeout,
        )

    def __enter__(self) -> DiscordClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # -- transport ---------------------------------------------------------

    def _send(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        """One HTTP call, with the single 429-retry and the rate-limit sleep.

        Returns the response even if it's an error; callers decide how to
        turn it into an exception (most go through `_request`, `search`
        intercepts code 110000 first).
        """
        resp = self._client.request(method, url, **kwargs)
        if resp.status_code == 429:
            self._sleep(_retry_after_seconds(resp))
            resp = self._client.request(method, url, **kwargs)
        if resp.headers.get("X-RateLimit-Remaining") == "0":
            reset_after = resp.headers.get("X-RateLimit-Reset-After")
            if reset_after is not None:
                self._sleep(float(reset_after))
        return resp

    def _request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
        resp = self._send(method, url, **kwargs)
        if resp.is_error:
            raise DiscordAPIError(resp)
        return resp

    # -- identity -----------------------------------------------------------

    def me(self) -> dict:
        """The bot's own user object (GET /users/@me): id, username."""
        return self._request("GET", "/users/@me").json()

    # -- channels & threads --------------------------------------------------

    def guild_channels(self, guild_id: str) -> list[dict]:
        """All channels in a guild (GET /guilds/{id}/channels)."""
        return self._request("GET", f"/guilds/{guild_id}/channels").json()

    def active_threads(self, guild_id: str) -> list[dict]:
        """Active threads in a guild (GET /guilds/{id}/threads/active).

        Returns the "threads" array from Discord's response, dropping the
        accompanying thread-member list nothing here needs.
        """
        return self._request("GET", f"/guilds/{guild_id}/threads/active").json()["threads"]

    def archived_public_threads(self, channel_id: str) -> list[dict]:
        """Archived public threads for one channel/forum, first page only.

        GET /channels/{id}/threads/archived/public. Thread messages never
        appear in the parent channel's own /messages, and a forum channel's
        posts exist only as threads, so this and `active_threads` are the
        only way to discover forum discussions. Channels with more archived
        threads than one page holds would need `before`-cursor pagination,
        which is not implemented; a daily window never needs more than the
        first page.
        """
        return (
            self._request("GET", f"/channels/{channel_id}/threads/archived/public")
            .json()["threads"]
        )

    # -- messages -------------------------------------------------------------

    def messages(
        self,
        channel_id: str,
        after: str | None = None,
        before: str | None = None,
    ) -> Iterator[dict]:
        """Yield every message with snowflake in [after, before), oldest first.

        Discord's GET .../messages always returns one page newest-first, but
        paginating with `after` walks forward chronologically: each page
        holds the oldest still-unread slice, capped at `limit`, not the
        newest slice. To yield the whole range exactly once in a single
        well-defined order, each page is reversed before being yielded (so
        the generator's overall output is chronological, ascending by
        snowflake), and the next `after` cursor is the newest id in the page
        just read. `before` is enforced client-side rather than sent as a
        request parameter, since Discord treats `before`/`after` as mutually
        exclusive on one call.
        """
        cursor = after if after is not None else "0"
        before_int = int(before) if before is not None else None
        while True:
            page = self._request(
                "GET",
                f"/channels/{channel_id}/messages",
                params={"limit": _PAGE_LIMIT, "after": cursor},
            ).json()
            if not page:
                return
            page.reverse()
            for msg in page:
                if before_int is not None and int(msg["id"]) >= before_int:
                    return
                yield msg
            cursor = page[-1]["id"]
            if len(page) < _PAGE_LIMIT:
                return

    # -- search -----------------------------------------------------------

    def search(self, guild_id: str, query: str, limit: int = 25) -> dict:
        """GET /guilds/{id}/messages/search.

        Raises SearchNotIndexed on Discord error code 110000 instead of the
        generic DiscordAPIError, so the CLI can print an explanation instead
        of a raw error body.
        """
        resp = self._send(
            "GET",
            f"/guilds/{guild_id}/messages/search",
            params={"content": query, "limit": limit},
        )
        if resp.is_error:
            body = _safe_json(resp)
            if body.get("code") == SEARCH_NOT_INDEXED_CODE:
                raise SearchNotIndexed(guild_id, body.get("message", "not indexed"))
            raise DiscordAPIError(resp)
        return resp.json()

    # -- writes -------------------------------------------------------------

    def post_message(
        self,
        channel_id: str,
        content: str | None = None,
        embeds: list[dict] | None = None,
    ) -> dict:
        """POST /channels/{id}/messages. Always sends allowed_mentions: {"parse": []}."""
        body: dict = {"allowed_mentions": {"parse": []}}
        if content is not None:
            body["content"] = content
        if embeds is not None:
            body["embeds"] = embeds
        return self._request("POST", f"/channels/{channel_id}/messages", json=body).json()

    def start_thread(self, channel_id: str, message_id: str, name: str) -> dict:
        """POST /channels/{channel_id}/messages/{message_id}/threads.

        Carries no message content, but still sends allowed_mentions so the
        no-accidental-mentions invariant holds unconditionally across every
        write helper, per project policy, not only the ones where it's
        semantically load-bearing.
        """
        body = {"name": name, "allowed_mentions": {"parse": []}}
        return self._request(
            "POST",
            f"/channels/{channel_id}/messages/{message_id}/threads",
            json=body,
        ).json()
