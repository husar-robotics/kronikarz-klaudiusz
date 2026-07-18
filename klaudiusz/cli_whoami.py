"""`whoami` subcommand: identity debugging for the resolved Discord token.

Two bot identities exist: the writer ("Klaudiusz", can post) and the read-only
reader ("Klaudiusz Reader", shared with beta users). `whoami` reports which
token the other commands would use and which bot it belongs to.
"""

from __future__ import annotations

import argparse
import sys

from . import config as config_module
from .discord_api import DiscordAPIError, DiscordClient


def register(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
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
