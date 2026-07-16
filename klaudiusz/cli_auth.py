"""`auth` and `whoami` subcommands: keychain token storage and identity debugging.

Two bot identities exist: the writer ("Klaudiusz", can post) and the read-only
reader ("Klaudiusz Reader", shared with beta users). `auth` stores either token
in the OS keychain so nobody exports secrets in their shell; `whoami` reports
which token the other commands would use and which bot it belongs to.
"""

from __future__ import annotations

import argparse
import sys
from getpass import getpass

from . import config as config_module
from .discord_api import DiscordAPIError, DiscordClient


def register(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    _register_auth(subparsers)
    _register_whoami(subparsers)


# -- auth ---------------------------------------------------------------------


def _register_auth(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = subparsers.add_parser("auth", help="store a Discord bot token in the OS keychain")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--writer",
        action="store_true",
        help="store the writer bot token (default: the reader token)",
    )
    group.add_argument(
        "--clear",
        action="store_true",
        help="delete both stored tokens from the keychain",
    )
    parser.set_defaults(func=_cmd_auth)


def _cmd_auth(args: argparse.Namespace) -> int:
    if args.clear:
        for entry in (config_module.KEYRING_WRITER_ENTRY, config_module.KEYRING_READER_ENTRY):
            removed = config_module._keyring_delete(entry)
            state = "removed" if removed else "nothing stored"
            print(f"[OK] keychain {config_module.KEYRING_SERVICE}/{entry}: {state}")
        return 0

    tier = "writer" if args.writer else "reader"
    entry = (
        config_module.KEYRING_WRITER_ENTRY if args.writer else config_module.KEYRING_READER_ENTRY
    )
    token = getpass(f"Paste the {tier} bot token (input hidden): ").strip()
    if not token:
        sys.exit("[FAIL] empty token; nothing stored")

    username = _verify(token)
    config_module._keyring_set(entry, token)
    print(
        f"[OK] verified as {username}; stored the {tier} token in "
        f"keychain {config_module.KEYRING_SERVICE}/{entry}"
    )
    return 0


def _verify(token: str) -> str:
    """The token's bot username, or a loud exit when Discord rejects it."""
    with DiscordClient(token) as client:
        try:
            user = client.me()
        except DiscordAPIError as exc:
            if exc.status_code == 401:
                sys.exit("[FAIL] Discord rejected the token (401 Unauthorized); nothing stored")
            raise
    return user["username"]


# -- whoami -------------------------------------------------------------------


def _register_whoami(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = subparsers.add_parser(
        "whoami", help="show which bot token the other commands would use"
    )
    parser.set_defaults(func=_cmd_whoami)


def _cmd_whoami(args: argparse.Namespace) -> int:
    resolved = config_module.resolve_token()
    with DiscordClient(resolved.token) as client:
        try:
            user = client.me()
        except DiscordAPIError as exc:
            if exc.status_code == 401:
                sys.exit(
                    f"[FAIL] token from {resolved.source} was rejected by Discord "
                    "(401 Unauthorized)"
                )
            raise
    print(f"{user['username']} (id {user['id']})")
    print(f"tier:   {resolved.tier}")
    print(f"source: {resolved.source}")
    return 0
