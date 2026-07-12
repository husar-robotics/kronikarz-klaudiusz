"""`klaudiusz` CLI entrypoint: an argparse skeleton later tasks register subcommands into."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

from . import cli_context, cli_read

PACKAGE_NAME = "klaudiusz"
FALLBACK_VERSION = "0.0.0+unknown"

# Each entry wires one subcommand's parser and handler. Later tasks append
# here instead of touching build_parser, so the registration order stays the
# single place that defines `klaudiusz --help`'s command list.
SubcommandRegistrar = Callable[["argparse._SubParsersAction[argparse.ArgumentParser]"], None]


def _package_version() -> str:
    try:
        return _pkg_version(PACKAGE_NAME)
    except PackageNotFoundError:
        return FALLBACK_VERSION


def _cmd_version(args: argparse.Namespace) -> int:
    print(_package_version())
    return 0


def _register_version(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = subparsers.add_parser("version", help="print the installed package version")
    parser.set_defaults(func=_cmd_version)


SUBCOMMANDS: list[SubcommandRegistrar] = [_register_version, cli_read.register, cli_context.register]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="klaudiusz",
        description="Discord <-> LLM bridge: ingestion, newsletter, and research-log CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for register in SUBCOMMANDS:
        register(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
