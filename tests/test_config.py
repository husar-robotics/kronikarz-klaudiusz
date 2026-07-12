from __future__ import annotations

import pytest

from klaudiusz.config import Config, bot_token, load_config

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
