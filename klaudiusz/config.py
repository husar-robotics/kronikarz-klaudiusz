"""Typed access to config.toml and to secrets in the environment or OS keychain."""

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

_REPO_ROOT_CONFIG = Path(__file__).resolve().parent.parent / "config.toml"
_PACKAGED_CONFIG = Path(__file__).resolve().parent / "config.toml"

# A dev checkout reads the repo-root config.toml; an installed wheel (uvx from
# another repo) has no repo root, so the wheel bundles a copy inside the
# package and that copy is the fallback.
DEFAULT_CONFIG_PATH = _REPO_ROOT_CONFIG if _REPO_ROOT_CONFIG.is_file() else _PACKAGED_CONFIG

# The .env sits next to the repo-root config.toml. In an installed wheel there
# is no repo root, so this path won't exist and load_env is a no-op there.
DEFAULT_ENV_PATH = _REPO_ROOT_CONFIG.parent / ".env"


def load_env(path: str | Path | None = None) -> None:
    """Populate the environment from a .env file so the DISCORD_*_TOKEN secrets
    don't need a manual `source` before each run.

    Real environment variables always win over the file (override=False), and a
    missing file is a silent no-op, so token resolution then falls through to the
    keychain exactly as before. Called once at process entry (see cli.run and
    smoke.py), never at import time, which keeps tests that drive main() hermetic.
    """
    from dotenv import load_dotenv

    load_dotenv(DEFAULT_ENV_PATH if path is None else path, override=False)


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


TokenTier = Literal["writer", "reader"]

KEYRING_SERVICE = "klaudiusz"
KEYRING_WRITER_ENTRY = "discord-bot-token"
KEYRING_READER_ENTRY = "discord-reader-token"


@dataclass(frozen=True)
class ResolvedToken:
    token: str
    tier: TokenTier
    source: str  # "env:<VAR>" or "keychain:klaudiusz/<entry>", printed verbatim by whoami


def _keyring_get(entry: str) -> str | None:
    """A stored token, or None when there is nothing usable.

    Any keyring failure (module missing, no Secret Service on a headless box,
    locked keychain) degrades to None so resolution falls through to the next
    source instead of crashing. An empty stored value counts as absent.
    """
    try:
        import keyring

        value = keyring.get_password(KEYRING_SERVICE, entry)
    except Exception:
        return None
    return value or None


def _keyring_set(entry: str, value: str) -> None:
    """Store a token, or die loudly: `auth` must never silently not-store."""
    try:
        import keyring

        keyring.set_password(KEYRING_SERVICE, entry, value)
    except Exception as exc:
        sys.exit(f"[FAIL] could not store the token in the OS keychain: {exc}")


def _keyring_delete(entry: str) -> bool:
    """Delete a stored token; True if one existed, False if none did."""
    try:
        import keyring
        import keyring.errors
    except Exception as exc:
        sys.exit(f"[FAIL] could not delete the token from the OS keychain: {exc}")
    try:
        keyring.delete_password(KEYRING_SERVICE, entry)
    except keyring.errors.PasswordDeleteError:
        return False
    except Exception as exc:
        sys.exit(f"[FAIL] could not delete the token from the OS keychain: {exc}")
    return True


def hvsr_token() -> str | None:
    """HVSR_TOKEN (the fine-grained GitHub PAT for shrek-dog), or None when absent.

    Reads the process environment only: `load_env` has already folded the
    repo-root .env into it at CLI entry, and that also puts the value where
    child processes need it — git's inline credential helper reads
    $HVSR_TOKEN inside git's own subprocess. An empty value counts as absent.
    """
    return os.environ.get("HVSR_TOKEN") or None


def resolve_token(require_write: bool = False) -> ResolvedToken:
    """The first token found, writer sources before reader sources.

    Read-only commands must be able to import this module and build a config
    without a token present, so the token is fetched lazily by callers that
    actually need to talk to Discord, never at import time.
    """
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if token:
        return ResolvedToken(token, "writer", "env:DISCORD_BOT_TOKEN")

    token = _keyring_get(KEYRING_WRITER_ENTRY)
    if token:
        return ResolvedToken(token, "writer", f"keychain:{KEYRING_SERVICE}/{KEYRING_WRITER_ENTRY}")

    if require_write:
        sys.exit(
            "[FAIL] this command writes to Discord and needs the writer token; "
            "run 'klaudiusz auth --writer' or set DISCORD_BOT_TOKEN in the environment"
        )

    token = os.environ.get("DISCORD_READER_TOKEN")
    if token:
        return ResolvedToken(token, "reader", "env:DISCORD_READER_TOKEN")

    token = _keyring_get(KEYRING_READER_ENTRY)
    if token:
        return ResolvedToken(token, "reader", f"keychain:{KEYRING_SERVICE}/{KEYRING_READER_ENTRY}")

    sys.exit(
        "[FAIL] no Discord token found; run 'klaudiusz auth' to store the reader token, "
        "or set DISCORD_BOT_TOKEN / DISCORD_READER_TOKEN in the environment"
    )


def bot_token(require_write: bool = False) -> str:
    return resolve_token(require_write=require_write).token
