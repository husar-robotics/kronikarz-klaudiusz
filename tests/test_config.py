from __future__ import annotations

import pytest

from klaudiusz import config as config_module
from klaudiusz.config import (
    Config,
    bot_token,
    load_config,
    resolve_token,
)

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


def test_resolve_env_writer_wins_over_env_reader(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "env-writer")
    monkeypatch.setenv("DISCORD_READER_TOKEN", "env-reader")

    resolved = resolve_token()

    assert resolved.token == "env-writer"
    assert resolved.tier == "writer"
    assert resolved.source == "env:DISCORD_BOT_TOKEN"


def test_resolve_env_reader_only(monkeypatch):
    monkeypatch.setenv("DISCORD_READER_TOKEN", "env-reader")

    resolved = resolve_token()

    assert resolved.token == "env-reader"
    assert resolved.tier == "reader"
    assert resolved.source == "env:DISCORD_READER_TOKEN"


def test_resolve_nothing_anywhere_exits_with_remediation():
    with pytest.raises(SystemExit) as excinfo:
        resolve_token()

    message = str(excinfo.value)
    assert "DISCORD_BOT_TOKEN" in message
    assert "DISCORD_READER_TOKEN" in message


def test_require_write_satisfied_by_env_writer(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "env-writer")

    resolved = resolve_token(require_write=True)

    assert resolved.token == "env-writer"
    assert resolved.tier == "writer"


def test_require_write_rejects_reader_sources(monkeypatch):
    monkeypatch.setenv("DISCORD_READER_TOKEN", "env-reader")

    with pytest.raises(SystemExit) as excinfo:
        resolve_token(require_write=True)

    message = str(excinfo.value)
    assert "writes to Discord" in message
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


# -- HVSR_TOKEN resolution (env, populated by load_env at CLI entry) --------------


def test_hvsr_token_from_env(monkeypatch):
    monkeypatch.setenv("HVSR_TOKEN", "from-env")

    assert config_module.hvsr_token() == "from-env"


def test_hvsr_token_absent_is_none():
    assert config_module.hvsr_token() is None


def test_hvsr_token_empty_counts_as_absent(monkeypatch):
    monkeypatch.setenv("HVSR_TOKEN", "")

    assert config_module.hvsr_token() is None


def test_load_env_populates_hvsr_token(tmp_path, monkeypatch):
    monkeypatch.delenv("HVSR_TOKEN", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text('HVSR_TOKEN="dotenv-file-token"\n')

    config_module.load_env(env_file)

    assert config_module.hvsr_token() == "dotenv-file-token"


def test_load_env_never_overrides_real_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("HVSR_TOKEN", "from-env")
    env_file = tmp_path / ".env"
    env_file.write_text('HVSR_TOKEN="dotenv-file-token"\n')

    config_module.load_env(env_file)

    assert config_module.hvsr_token() == "from-env"
