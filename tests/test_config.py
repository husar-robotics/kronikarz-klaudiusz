from __future__ import annotations

import sys

import pytest

from klaudiusz import config as config_module
from klaudiusz.config import (
    KEYRING_READER_ENTRY,
    KEYRING_WRITER_ENTRY,
    Config,
    bot_token,
    load_config,
    resolve_token,
)

# Bound at import time, before conftest's autouse fixture patches the module
# attributes away: these are the real keyring helpers, for the fallback tests.
real_keyring_get = config_module._keyring_get
real_keyring_set = config_module._keyring_set
real_keyring_delete = config_module._keyring_delete

VALID_TOML = """
[discord]
guild_id = "111"
newsletter_channel_id = "222"
ignore_channels = ["bot-news"]

[shrek_dog]
repo = "husar-robotics/shrek-dog"
log_dir = "docs/research-log"

[schedule]
timezone = "Europe/Warsaw"
quiet_day_message_threshold = 10
"""


def test_load_config_happy_path(tmp_path, monkeypatch):
    config_path = tmp_path / "config.toml"
    config_path.write_text(VALID_TOML)
    monkeypatch.setenv("KLAUDIUSZ_CONFIG", str(config_path))

    config = load_config()

    assert isinstance(config, Config)
    assert config.discord.guild_id == "111"
    assert config.discord.newsletter_channel_id == "222"
    assert config.discord.ignore_channels == ("bot-news",)
    assert config.shrek_dog.repo == "husar-robotics/shrek-dog"
    assert config.shrek_dog.log_dir == "docs/research-log"
    assert config.schedule.timezone == "Europe/Warsaw"
    assert config.schedule.quiet_day_message_threshold == 10


def test_load_config_explicit_path_overrides_env(tmp_path, monkeypatch):
    config_path = tmp_path / "config.toml"
    config_path.write_text(VALID_TOML)
    monkeypatch.setenv("KLAUDIUSZ_CONFIG", str(tmp_path / "does-not-exist.toml"))

    config = load_config(config_path)

    assert config.discord.guild_id == "111"


def test_load_config_missing_file_exits(tmp_path, monkeypatch):
    monkeypatch.setenv("KLAUDIUSZ_CONFIG", str(tmp_path / "missing.toml"))

    with pytest.raises(SystemExit) as excinfo:
        load_config()

    assert "missing.toml" in str(excinfo.value)


def test_load_config_missing_key_exits(tmp_path, monkeypatch):
    config_path = tmp_path / "config.toml"
    config_path.write_text('[discord]\nguild_id = "111"\n')
    monkeypatch.setenv("KLAUDIUSZ_CONFIG", str(config_path))

    with pytest.raises(SystemExit):
        load_config()


def test_bot_token_missing_exits(monkeypatch):
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)

    with pytest.raises(SystemExit) as excinfo:
        bot_token()

    assert "DISCORD_BOT_TOKEN" in str(excinfo.value)


def test_bot_token_present(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "secret-token")

    assert bot_token() == "secret-token"


def _keychain(entries: dict[str, str]):
    return lambda entry: entries.get(entry)


def test_resolve_env_writer_wins_over_everything(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "env-writer")
    monkeypatch.setenv("DISCORD_READER_TOKEN", "env-reader")
    monkeypatch.setattr(
        config_module,
        "_keyring_get",
        _keychain({KEYRING_WRITER_ENTRY: "kc-writer", KEYRING_READER_ENTRY: "kc-reader"}),
    )

    resolved = resolve_token()

    assert resolved.token == "env-writer"
    assert resolved.tier == "writer"
    assert resolved.source == "env:DISCORD_BOT_TOKEN"


def test_resolve_keychain_writer_when_no_env_writer(monkeypatch):
    monkeypatch.setattr(
        config_module, "_keyring_get", _keychain({KEYRING_WRITER_ENTRY: "kc-writer"})
    )

    resolved = resolve_token()

    assert resolved.token == "kc-writer"
    assert resolved.tier == "writer"
    assert resolved.source == "keychain:klaudiusz/discord-bot-token"


def test_resolve_keychain_writer_beats_env_reader(monkeypatch):
    monkeypatch.setenv("DISCORD_READER_TOKEN", "env-reader")
    monkeypatch.setattr(
        config_module, "_keyring_get", _keychain({KEYRING_WRITER_ENTRY: "kc-writer"})
    )

    resolved = resolve_token()

    assert resolved.token == "kc-writer"
    assert resolved.tier == "writer"


def test_resolve_env_reader_only(monkeypatch):
    monkeypatch.setenv("DISCORD_READER_TOKEN", "env-reader")

    resolved = resolve_token()

    assert resolved.token == "env-reader"
    assert resolved.tier == "reader"
    assert resolved.source == "env:DISCORD_READER_TOKEN"


def test_resolve_keychain_reader_only(monkeypatch):
    monkeypatch.setattr(
        config_module, "_keyring_get", _keychain({KEYRING_READER_ENTRY: "kc-reader"})
    )

    resolved = resolve_token()

    assert resolved.token == "kc-reader"
    assert resolved.tier == "reader"
    assert resolved.source == "keychain:klaudiusz/discord-reader-token"


def test_resolve_nothing_anywhere_exits_with_remediation():
    with pytest.raises(SystemExit) as excinfo:
        resolve_token()

    message = str(excinfo.value)
    assert "klaudiusz auth" in message
    assert "DISCORD_BOT_TOKEN" in message
    assert "DISCORD_READER_TOKEN" in message


def test_require_write_satisfied_by_keychain_writer(monkeypatch):
    monkeypatch.setattr(
        config_module, "_keyring_get", _keychain({KEYRING_WRITER_ENTRY: "kc-writer"})
    )

    resolved = resolve_token(require_write=True)

    assert resolved.token == "kc-writer"
    assert resolved.tier == "writer"


def test_require_write_rejects_reader_sources(monkeypatch):
    monkeypatch.setenv("DISCORD_READER_TOKEN", "env-reader")
    monkeypatch.setattr(
        config_module, "_keyring_get", _keychain({KEYRING_READER_ENTRY: "kc-reader"})
    )

    with pytest.raises(SystemExit) as excinfo:
        resolve_token(require_write=True)

    message = str(excinfo.value)
    assert "auth --writer" in message
    assert "DISCORD_BOT_TOKEN" in message


def test_empty_env_var_falls_through_to_next_source(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "")
    monkeypatch.setenv("DISCORD_READER_TOKEN", "env-reader")

    resolved = resolve_token()

    assert resolved.token == "env-reader"
    assert resolved.tier == "reader"


def test_bot_token_delegates_to_resolve(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "env-writer")

    assert bot_token() == "env-writer"
    assert bot_token(require_write=True) == "env-writer"


# -- the real keyring helpers (conftest patches them away; these tests bind
# -- them at import time and exercise headless/broken-backend behavior) --


def test_keyring_get_none_when_import_fails(monkeypatch):
    monkeypatch.setitem(sys.modules, "keyring", None)

    assert real_keyring_get("anything") is None


def test_keyring_get_none_when_backend_raises(monkeypatch):
    import keyring

    def boom(service, entry):
        raise RuntimeError("no Secret Service on this box")

    monkeypatch.setattr(keyring, "get_password", boom)

    assert real_keyring_get(KEYRING_READER_ENTRY) is None


def test_keyring_get_treats_empty_stored_value_as_absent(monkeypatch):
    import keyring

    monkeypatch.setattr(keyring, "get_password", lambda service, entry: "")

    assert real_keyring_get(KEYRING_READER_ENTRY) is None


def test_keyring_get_returns_stored_value(monkeypatch):
    import keyring

    monkeypatch.setattr(keyring, "get_password", lambda service, entry: "kc-token")

    assert real_keyring_get(KEYRING_READER_ENTRY) == "kc-token"


def test_keyring_set_stores_under_service_and_entry(monkeypatch):
    import keyring

    calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(keyring, "set_password", lambda *args: calls.append(args))

    real_keyring_set(KEYRING_READER_ENTRY, "tok")

    assert calls == [("klaudiusz", KEYRING_READER_ENTRY, "tok")]


def test_keyring_set_loud_on_broken_backend(monkeypatch):
    import keyring

    def boom(service, entry, value):
        raise RuntimeError("keychain locked")

    monkeypatch.setattr(keyring, "set_password", boom)

    with pytest.raises(SystemExit) as excinfo:
        real_keyring_set(KEYRING_READER_ENTRY, "tok")

    assert "[FAIL] could not store" in str(excinfo.value)


def test_keyring_delete_true_when_entry_existed(monkeypatch):
    import keyring

    monkeypatch.setattr(keyring, "delete_password", lambda service, entry: None)

    assert real_keyring_delete(KEYRING_READER_ENTRY) is True


def test_keyring_delete_false_when_nothing_stored(monkeypatch):
    import keyring
    import keyring.errors

    def missing(service, entry):
        raise keyring.errors.PasswordDeleteError("no such entry")

    monkeypatch.setattr(keyring, "delete_password", missing)

    assert real_keyring_delete(KEYRING_READER_ENTRY) is False


def test_keyring_delete_loud_on_broken_backend(monkeypatch):
    import keyring

    def boom(service, entry):
        raise RuntimeError("keychain locked")

    monkeypatch.setattr(keyring, "delete_password", boom)

    with pytest.raises(SystemExit) as excinfo:
        real_keyring_delete(KEYRING_READER_ENTRY)

    assert "[FAIL] could not delete" in str(excinfo.value)
