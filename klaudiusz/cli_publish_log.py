"""`publish-log` subcommand: validate a log bundle and PR it into shrek-dog.

The pipeline splits into three testable layers: `validate_bundle` (pure),
`apply_bundle` (filesystem only), and `publish_bundle` (git + gh side effects,
with a clone-URL override so tests can point it at a local bare repo).

Secret handling: the SHREK_DOG_TOKEN value must never appear in argv, URLs,
logs, or files. Git auth goes through an inline credential helper whose shell
reads the env var inside git's own subprocess; `gh` gets it via GH_TOKEN in
the child environment.
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import config as config_module
from .config import Config

NEWSLETTER_ARCHIVE_URL = (
    "https://github.com/husar-robotics/kronikarz-klaudiusz/blob/main/newsletters/{date}.md"
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_H2_RE = re.compile(r"^##(?!#)")
_TAGGED_BULLET_RE = re.compile(r"^- \*\*(Decision|Result|Direction|Question|Resource):\*\*")
_LINK_TARGET_RE = re.compile(r"\]\(([^)\s]+)\)")

# The helper makes git's own shell expand the token from the environment, so
# the value never enters this process's argv; the empty first helper disables
# any helpers inherited from the user's git config.
_CREDENTIAL_ARGS = (
    "-c",
    "credential.helper=",
    "-c",
    'credential.helper=!f() { echo username=x-access-token; echo "password=$SHREK_DOG_TOKEN"; }; f',
)


@dataclass(frozen=True)
class Bundle:
    """A validated log bundle: the entry text plus its details files."""

    root: Path
    date: str
    entry_text: str
    details: tuple[str, ...]  # bundle-relative posix paths, e.g. "details/x.md"


# -- validation (pure) --------------------------------------------------------


def validate_bundle(bundle_dir: str | Path, date: str) -> Bundle:
    """Check the bundle against the log-bundle contract; exit loudly on any violation."""
    bundle_dir = Path(bundle_dir)
    entry_path = bundle_dir / "entry.md"
    if not entry_path.is_file():
        sys.exit(f"[FAIL] {entry_path} not found; a log bundle needs an entry.md")

    text = entry_path.read_text(encoding="utf-8")
    non_blank = [line for line in text.splitlines() if line.strip()]
    if not non_blank:
        sys.exit(f"[FAIL] {entry_path} is empty")

    expected_heading = f"## {date}"
    if non_blank[0].rstrip() != expected_heading:
        sys.exit(
            f"[FAIL] entry.md must open with {expected_heading!r}; first line is {non_blank[0]!r}"
        )
    for line in non_blank[1:]:
        if _H2_RE.match(line):
            sys.exit(
                f"[FAIL] entry.md must be a single {expected_heading!r} section; "
                f"found a second heading: {line!r}"
            )
        if line[0] in " \t":
            continue  # continuation line indented under a bullet
        if not _TAGGED_BULLET_RE.match(line):
            sys.exit(
                "[FAIL] entry.md has an untagged bullet; every top-level bullet must start "
                "with one of - **Decision:** / - **Result:** / - **Direction:** / "
                f"- **Question:** / - **Resource:**; got: {line!r}"
            )

    referenced: set[str] = set()
    for target in _LINK_TARGET_RE.findall(text):
        target = target.split("#", 1)[0]
        target = target.removeprefix("./")
        if not target.startswith("details/"):
            continue
        referenced.add(target)
        if not (bundle_dir / target).is_file():
            sys.exit(f"[FAIL] entry.md links to {target} but the bundle has no such file")

    details_dir = bundle_dir / "details"
    present: list[str] = []
    if details_dir.is_dir():
        present = sorted(f"details/{p.name}" for p in details_dir.iterdir() if p.is_file())
    for rel in present:
        if rel not in referenced:
            sys.exit(f"[FAIL] {rel} is not referenced from entry.md; link it or remove it")

    return Bundle(root=bundle_dir, date=date, entry_text=text, details=tuple(present))


# -- apply (filesystem only) ---------------------------------------------------


def _has_date_heading(text: str, date: str) -> bool:
    return any(line.rstrip() == f"## {date}" for line in text.splitlines())


def apply_bundle(bundle: Bundle, checkout_dir: Path, log_dir: str, date: str) -> list[str]:
    """Write the entry and details into a checkout; return the repo-relative paths touched."""
    month = date[:7]
    month_rel = f"{log_dir}/{month}.md"
    month_file = checkout_dir / month_rel
    month_file.parent.mkdir(parents=True, exist_ok=True)

    entry = bundle.entry_text.rstrip() + "\n"
    if month_file.is_file():
        existing = month_file.read_text(encoding="utf-8")
        month_file.write_text(existing.rstrip("\n") + "\n\n" + entry, encoding="utf-8")
    else:
        month_file.write_text(f"# Research log — {month}\n\n" + entry, encoding="utf-8")

    touched = [month_rel]
    for rel in bundle.details:
        dest = checkout_dir / log_dir / rel
        if dest.exists():
            sys.exit(f"[FAIL] {log_dir}/{rel} already exists in the checkout; refusing to overwrite")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(bundle.root / rel, dest)
        touched.append(f"{log_dir}/{rel}")
    return touched


# -- git/gh orchestration --------------------------------------------------------


def shrek_dog_token() -> str:
    """Read SHREK_DOG_TOKEN from the environment; loud error naming the variable when absent."""
    token = os.environ.get("SHREK_DOG_TOKEN")
    if not token:
        sys.exit("[FAIL] set SHREK_DOG_TOKEN in the environment")
    return token


def _run_git(args: list[str], cwd: Path | None = None) -> str:
    """Run git inheriting the environment (the credential helper reads the token from it)."""
    try:
        result = subprocess.run(
            ["git", *args], capture_output=True, text=True, check=False, cwd=cwd
        )
    except FileNotFoundError:
        sys.exit("[FAIL] git not found; install git")
    if result.returncode != 0:
        sys.exit(f"[FAIL] git {' '.join(args)} exited {result.returncode}: {result.stderr.strip()}")
    return result.stdout


def _create_pr(repo: str, branch: str, date: str, token: str) -> str:
    """Open the PR via gh (token passed only through GH_TOKEN in the child env); return its URL."""
    body = (
        f"Daily research-log entry for {date}, generated from the day's Discord "
        "and repo activity.\n\n"
        f"Newsletter archive for the day: {NEWSLETTER_ARCHIVE_URL.format(date=date)}\n\n"
        "🤖 Generated with [Claude Code](https://claude.com/claude-code)\n"
    )
    cmd = [
        "gh",
        "pr",
        "create",
        "--repo",
        repo,
        "--head",
        branch,
        "--title",
        f"research log: {date}",
        "--body",
        body,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "GH_TOKEN": token},
        )
    except FileNotFoundError:
        sys.exit("[FAIL] gh CLI not found; install it")
    if result.returncode != 0:
        sys.exit(f"[FAIL] gh pr create exited {result.returncode}: {result.stderr.strip()}")
    return result.stdout.strip()


def publish_bundle(bundle: Bundle, cfg: Config, *, clone_url: str | None = None) -> str:
    """Clone shrek-dog, apply the bundle, push the branch, open the PR; return the PR URL.

    `clone_url` exists only so tests can clone from a local bare repo; the CLI
    always derives the URL from config, never from user input.
    """
    token = shrek_dog_token()
    repo = cfg.shrek_dog.repo
    url = clone_url or f"https://github.com/{repo}.git"
    branch = f"research-log/{bundle.date}"
    month = bundle.date[:7]
    month_rel = f"{cfg.shrek_dog.log_dir}/{month}.md"

    with tempfile.TemporaryDirectory(prefix="klaudiusz-publish-log-") as tmp:
        checkout = Path(tmp) / "shrek-dog"
        _run_git([*_CREDENTIAL_ARGS, "clone", "--depth", "1", url, str(checkout)])

        month_file = checkout / month_rel
        if month_file.is_file() and _has_date_heading(
            month_file.read_text(encoding="utf-8"), bundle.date
        ):
            sys.exit(
                f"[FAIL] {month_rel} already has a '## {bundle.date}' section; "
                "refusing to publish the same date twice"
            )

        _run_git(["checkout", "-b", branch], cwd=checkout)
        touched = apply_bundle(bundle, checkout, cfg.shrek_dog.log_dir, bundle.date)
        _run_git(["add", "--", *touched], cwd=checkout)
        _run_git(["commit", "-m", f"research log: {bundle.date}"], cwd=checkout)
        _run_git([*_CREDENTIAL_ARGS, "push", "origin", branch], cwd=checkout)
        return _create_pr(repo, branch, bundle.date, token)


# -- CLI ------------------------------------------------------------------------


def _parse_date(value: str) -> str:
    if not _DATE_RE.match(value):
        sys.exit(f"[FAIL] --date must be YYYY-MM-DD, got {value!r}")
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        sys.exit(f"[FAIL] --date is not a real calendar date: {value!r}")
    return value


def _print_plan(bundle: Bundle, cfg: Config) -> None:
    month = bundle.date[:7]
    print("Dry run — bundle validated; nothing cloned, committed, or pushed.")
    print(f"  repo:       {cfg.shrek_dog.repo}")
    print(f"  branch:     research-log/{bundle.date}")
    print(f"  month file: {cfg.shrek_dog.log_dir}/{month}.md (append the '## {bundle.date}' entry)")
    if bundle.details:
        for rel in bundle.details:
            print(f"  details:    {cfg.shrek_dog.log_dir}/{rel}")
    else:
        print("  details:    none")


def _cmd_publish_log(args: argparse.Namespace) -> int:
    entry_date = _parse_date(args.date)
    cfg = config_module.load_config()
    bundle = validate_bundle(Path(args.dir), entry_date)
    if args.dry_run:
        _print_plan(bundle, cfg)
        return 0
    pr_url = publish_bundle(bundle, cfg)
    print(pr_url)
    return 0


def register(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    """Wire the publish-log subcommand into the shared parser."""
    parser = subparsers.add_parser(
        "publish-log", help="validate a log bundle and open a research-log PR to shrek-dog"
    )
    parser.add_argument("dir", help="log bundle directory (entry.md + optional details/)")
    parser.add_argument("--date", required=True, help="the entry's date, YYYY-MM-DD")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and print the plan without cloning or pushing anything",
    )
    parser.set_defaults(func=_cmd_publish_log)
