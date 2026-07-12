"""Typed access to config.toml and to secrets in the environment."""

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT_CONFIG = Path(__file__).resolve().parent.parent / "config.toml"
_PACKAGED_CONFIG = Path(__file__).resolve().parent / "config.toml"

# A dev checkout reads the repo-root config.toml; an installed wheel (uvx from
# another repo) has no repo root, so the wheel bundles a copy inside the
# package and that copy is the fallback.
DEFAULT_CONFIG_PATH = _REPO_ROOT_CONFIG if _REPO_ROOT_CONFIG.is_file() else _PACKAGED_CONFIG


@dataclass(frozen=True)
class DiscordConfig:
    guild_id: str
    newsletter_channel_id: str
    ignore_channels: tuple[str, ...]


@dataclass(frozen=True)
class ShrekDogConfig:
    repo: str
    log_dir: str


@dataclass(frozen=True)
class ScheduleConfig:
    timezone: str
    quiet_day_message_threshold: int


@dataclass(frozen=True)
class Config:
    discord: DiscordConfig
    shrek_dog: ShrekDogConfig
    schedule: ScheduleConfig


def load_config(path: str | Path | None = None) -> Config:
    """Load config.toml.

    Path resolution order: explicit `path` argument, then the KLAUDIUSZ_CONFIG
    env var (how tests point at a fixture), then the repo root.
    """
    if path is None:
        path = os.environ.get("KLAUDIUSZ_CONFIG", DEFAULT_CONFIG_PATH)
    path = Path(path)
    if not path.is_file():
        sys.exit(f"[FAIL] config file not found: {path}")

    with path.open("rb") as f:
        raw = tomllib.load(f)

    try:
        discord = DiscordConfig(
            guild_id=raw["discord"]["guild_id"],
            newsletter_channel_id=raw["discord"]["newsletter_channel_id"],
            ignore_channels=tuple(raw["discord"].get("ignore_channels", [])),
        )
        shrek_dog = ShrekDogConfig(
            repo=raw["shrek_dog"]["repo"],
            log_dir=raw["shrek_dog"]["log_dir"],
        )
        schedule = ScheduleConfig(
            timezone=raw["schedule"]["timezone"],
            quiet_day_message_threshold=raw["schedule"]["quiet_day_message_threshold"],
        )
    except KeyError as exc:
        sys.exit(f"[FAIL] config file {path} is missing required key: {exc}")

    return Config(discord=discord, shrek_dog=shrek_dog, schedule=schedule)


def bot_token() -> str:
    """Read DISCORD_BOT_TOKEN from the environment.

    Read-only commands must be able to import this module and build a config
    without a token present, so the token is fetched lazily by callers that
    actually need to talk to Discord, never at import time.
    """
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        sys.exit("[FAIL] set DISCORD_BOT_TOKEN in the environment")
    return token
