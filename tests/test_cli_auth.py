from __future__ import annotations

import httpx
import pytest

from klaudiusz import cli_auth
from klaudiusz import config as config_module
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


@pytest.fixture
def keyring_recorder(monkeypatch):
    """Recording fakes over the conftest _forbid stubs."""
    record = {"set": [], "deleted": []}
    monkeypatch.setattr(
        config_module, "_keyring_set", lambda entry, value: record["set"].append((entry, value))
    )
    monkeypatch.setattr(
        config_module, "_keyring_delete", lambda entry: record["deleted"].append(entry) or True
    )
    return record


# -- auth ---------------------------------------------------------------------


def test_auth_default_stores_reader_token(monkeypatch, keyring_recorder, capsys):
    monkeypatch.setattr(cli_auth, "getpass", lambda prompt: "reader-tok")
    monkeypatch.setattr(cli_auth, "DiscordClient", make_fake_client())

    exit_code = main(["auth"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert keyring_recorder["set"] == [(config_module.KEYRING_READER_ENTRY, "reader-tok")]
    assert "Klaudiusz Reader" in out
    assert "reader" in out


def test_auth_writer_flag_stores_writer_token(monkeypatch, keyring_recorder):
    monkeypatch.setattr(cli_auth, "getpass", lambda prompt: "writer-tok")
    monkeypatch.setattr(
        cli_auth, "DiscordClient", make_fake_client(user={"id": "7", "username": "Klaudiusz"})
    )

    exit_code = main(["auth", "--writer"])

    assert exit_code == 0
    assert keyring_recorder["set"] == [(config_module.KEYRING_WRITER_ENTRY, "writer-tok")]


def test_auth_rejected_token_stores_nothing(monkeypatch, keyring_recorder):
    monkeypatch.setattr(cli_auth, "getpass", lambda prompt: "bad-tok")
    monkeypatch.setattr(cli_auth, "DiscordClient", make_fake_client(error=_401_error()))

    with pytest.raises(SystemExit) as excinfo:
        main(["auth"])

    assert "401" in str(excinfo.value)
    assert "nothing stored" in str(excinfo.value)
    assert keyring_recorder["set"] == []


@pytest.mark.parametrize("pasted", ["", "   ", "\n"])
def test_auth_empty_input_fails_before_any_call(monkeypatch, keyring_recorder, pasted):
    client_cls = make_fake_client()
    monkeypatch.setattr(cli_auth, "getpass", lambda prompt: pasted)
    monkeypatch.setattr(cli_auth, "DiscordClient", client_cls)

    with pytest.raises(SystemExit) as excinfo:
        main(["auth"])

    assert "empty token" in str(excinfo.value)
    assert client_cls.me_calls == 0
    assert keyring_recorder["set"] == []


def test_auth_strips_pasted_newline(monkeypatch, keyring_recorder):
    monkeypatch.setattr(cli_auth, "getpass", lambda prompt: "reader-tok\n")
    monkeypatch.setattr(cli_auth, "DiscordClient", make_fake_client())

    main(["auth"])

    assert keyring_recorder["set"] == [(config_module.KEYRING_READER_ENTRY, "reader-tok")]


def test_auth_never_prints_the_token(monkeypatch, keyring_recorder, capsys):
    monkeypatch.setattr(cli_auth, "getpass", lambda prompt: "sekret-tok-123")
    monkeypatch.setattr(cli_auth, "DiscordClient", make_fake_client())

    main(["auth"])

    assert "sekret-tok-123" not in capsys.readouterr().out


def test_auth_clear_deletes_both_entries(monkeypatch, keyring_recorder, capsys):
    exit_code = main(["auth", "--clear"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert keyring_recorder["deleted"] == [
        config_module.KEYRING_WRITER_ENTRY,
        config_module.KEYRING_READER_ENTRY,
    ]
    assert out.count("removed") == 2


def test_auth_clear_reports_when_nothing_was_stored(monkeypatch, capsys):
    monkeypatch.setattr(config_module, "_keyring_delete", lambda entry: False)

    exit_code = main(["auth", "--clear"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert out.count("nothing stored") == 2


def test_auth_writer_and_clear_are_mutually_exclusive():
    with pytest.raises(SystemExit) as excinfo:
        main(["auth", "--writer", "--clear"])

    assert excinfo.value.code == 2


# -- whoami -------------------------------------------------------------------


def test_whoami_reports_env_writer(monkeypatch, capsys):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "env-writer-tok")
    monkeypatch.setattr(
        cli_auth, "DiscordClient", make_fake_client(user={"id": "7", "username": "Klaudiusz"})
    )

    exit_code = main(["whoami"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Klaudiusz (id 7)" in out
    assert "tier:   writer" in out
    assert "source: env:DISCORD_BOT_TOKEN" in out


def test_whoami_reports_keychain_reader(monkeypatch, capsys):
    monkeypatch.setattr(
        config_module,
        "_keyring_get",
        lambda entry: "kc-reader" if entry == config_module.KEYRING_READER_ENTRY else None,
    )
    client_cls = make_fake_client()
    monkeypatch.setattr(cli_auth, "DiscordClient", client_cls)

    exit_code = main(["whoami"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert client_cls.tokens == ["kc-reader"]
    assert "tier:   reader" in out
    assert "source: keychain:klaudiusz/discord-reader-token" in out


def test_whoami_without_any_token_exits(monkeypatch):
    with pytest.raises(SystemExit) as excinfo:
        main(["whoami"])

    assert "no Discord token found" in str(excinfo.value)


def test_whoami_rejected_token_names_the_source(monkeypatch):
    monkeypatch.setenv("DISCORD_READER_TOKEN", "stale-tok")
    monkeypatch.setattr(cli_auth, "DiscordClient", make_fake_client(error=_401_error()))

    with pytest.raises(SystemExit) as excinfo:
        main(["whoami"])

    message = str(excinfo.value)
    assert "env:DISCORD_READER_TOKEN" in message
    assert "401" in message
