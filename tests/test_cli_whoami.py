from __future__ import annotations

import httpx
import pytest

from klaudiusz import cli_whoami
from klaudiusz.cli import main
from klaudiusz.discord_api import DiscordAPIError


def _401_error() -> DiscordAPIError:
    return DiscordAPIError(
        httpx.Response(
            401,
            request=httpx.Request("GET", "https://discord.com/api/v10/users/@me"),
            text="401: Unauthorized",
        )
    )


def make_fake_client(*, user: dict | None = None, error: Exception | None = None):
    """A DiscordClient stand-in class recording construction and me() calls."""

    class FakeClient:
        tokens: list[str] = []
        me_calls: int = 0

        def __init__(self, token: str, **kwargs: object) -> None:
            type(self).tokens.append(token)

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *exc_info: object) -> None:
            return None

        def me(self) -> dict:
            type(self).me_calls += 1
            if error is not None:
                raise error
            return user if user is not None else {"id": "42", "username": "Klaudiusz Reader"}

    return FakeClient


def test_whoami_reports_env_writer(monkeypatch, capsys):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "env-writer-tok")
    monkeypatch.setattr(
        cli_whoami, "DiscordClient", make_fake_client(user={"id": "7", "username": "Klaudiusz"})
    )

    exit_code = main(["whoami"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Klaudiusz (id 7)" in out
    assert "tier:   writer" in out
    assert "source: env:DISCORD_BOT_TOKEN" in out


def test_whoami_reports_env_reader(monkeypatch, capsys):
    monkeypatch.setenv("DISCORD_READER_TOKEN", "env-reader-tok")
    client_cls = make_fake_client()
    monkeypatch.setattr(cli_whoami, "DiscordClient", client_cls)

    exit_code = main(["whoami"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert client_cls.tokens == ["env-reader-tok"]
    assert "tier:   reader" in out
    assert "source: env:DISCORD_READER_TOKEN" in out


def test_whoami_without_any_token_exits(monkeypatch):
    with pytest.raises(SystemExit) as excinfo:
        main(["whoami"])

    assert "no Discord token found" in str(excinfo.value)


def test_whoami_rejected_token_names_the_source(monkeypatch):
    monkeypatch.setenv("DISCORD_READER_TOKEN", "stale-tok")
    monkeypatch.setattr(cli_whoami, "DiscordClient", make_fake_client(error=_401_error()))

    with pytest.raises(SystemExit) as excinfo:
        main(["whoami"])

    message = str(excinfo.value)
    assert "env:DISCORD_READER_TOKEN" in message
    assert "401" in message
