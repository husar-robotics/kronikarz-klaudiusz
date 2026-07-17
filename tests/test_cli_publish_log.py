from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import httpx
import pytest
import respx

from klaudiusz import cli_publish_log as cpl
from klaudiusz.cli import main
from klaudiusz.config import Config, DiscordConfig, ScheduleConfig, ShrekDogConfig

DATE = "2026-07-12"
REPO = "husar-robotics/shrek-dog"
LOG_DIR = "docs/research-log"
DETAILS_NAME = "2026-07-12-mjx-divergence.md"

GOOD_ENTRY = f"""## {DATE}
- **Decision:** leg actuators switch to QDD after the torque-density comparison
  ([discussion](https://discord.com/channels/1/2/3))
- **Result:** MJX run converged after the contact-parameter fix
  ([details](details/{DETAILS_NAME}))
- **Question:** sim2real friction gap unresolved
"""

CONFIG_TOML = f"""
[discord]
guild_id = "111"
newsletter_channel_id = "222"
ignore_channels = []

[shrek_dog]
repo = "{REPO}"
log_dir = "{LOG_DIR}"

[schedule]
timezone = "Europe/Warsaw"
quiet_day_message_threshold = 10
"""


def make_config() -> Config:
    return Config(
        discord=DiscordConfig(guild_id="111", newsletter_channel_id="222", ignore_channels=()),
        shrek_dog=ShrekDogConfig(repo=REPO, log_dir=LOG_DIR),
        schedule=ScheduleConfig(timezone="Europe/Warsaw", quiet_day_message_threshold=10),
    )


def make_bundle(
    tmp_path: Path,
    entry: str = GOOD_ENTRY,
    details: tuple[str, ...] = (DETAILS_NAME,),
) -> Path:
    bundle = tmp_path / "bundle"
    bundle.mkdir(exist_ok=True)
    (bundle / "entry.md").write_text(entry, encoding="utf-8")
    if details:
        (bundle / "details").mkdir(exist_ok=True)
        for name in details:
            (bundle / "details" / name).write_text(f"# {name}\n\nlong-form write-up\n")
    return bundle


# -- validation ----------------------------------------------------------------


def test_good_bundle_passes(tmp_path):
    bundle = cpl.validate_bundle(make_bundle(tmp_path), DATE)

    assert bundle.date == DATE
    assert bundle.entry_text == GOOD_ENTRY
    assert bundle.details == (f"details/{DETAILS_NAME}",)


def test_bundle_without_details_passes(tmp_path):
    entry = f"## {DATE}\n- **Direction:** week focus moves to sim2real\n"

    bundle = cpl.validate_bundle(make_bundle(tmp_path, entry=entry, details=()), DATE)

    assert bundle.details == ()


def test_missing_entry_md_fails(tmp_path):
    empty = tmp_path / "bundle"
    empty.mkdir()

    with pytest.raises(SystemExit) as excinfo:
        cpl.validate_bundle(empty, DATE)

    assert "entry.md" in str(excinfo.value)
    assert "not found" in str(excinfo.value)


def test_wrong_date_heading_fails(tmp_path):
    entry = "## 2026-07-11\n- **Result:** something\n"

    with pytest.raises(SystemExit) as excinfo:
        cpl.validate_bundle(make_bundle(tmp_path, entry=entry, details=()), DATE)

    message = str(excinfo.value)
    assert "must open with" in message
    assert f"## {DATE}" in message


def test_second_heading_fails(tmp_path):
    entry = f"## {DATE}\n- **Result:** something\n\n## another section\n- **Result:** more\n"

    with pytest.raises(SystemExit) as excinfo:
        cpl.validate_bundle(make_bundle(tmp_path, entry=entry, details=()), DATE)

    message = str(excinfo.value)
    assert "single" in message
    assert "second heading" in message


def test_untagged_bullet_fails(tmp_path):
    entry = f"## {DATE}\n- **Result:** fine\n- just a plain untagged bullet\n"

    with pytest.raises(SystemExit) as excinfo:
        cpl.validate_bundle(make_bundle(tmp_path, entry=entry, details=()), DATE)

    message = str(excinfo.value)
    assert "untagged bullet" in message
    assert "just a plain untagged bullet" in message


def test_missing_details_file_fails(tmp_path):
    entry = f"## {DATE}\n- **Result:** converged ([details](details/missing.md))\n"

    with pytest.raises(SystemExit) as excinfo:
        cpl.validate_bundle(make_bundle(tmp_path, entry=entry, details=()), DATE)

    message = str(excinfo.value)
    assert "details/missing.md" in message
    assert "no such file" in message


def test_orphan_details_file_fails(tmp_path):
    entry = f"## {DATE}\n- **Result:** no link to the details file here\n"

    with pytest.raises(SystemExit) as excinfo:
        cpl.validate_bundle(make_bundle(tmp_path, entry=entry, details=("orphan.md",)), DATE)

    message = str(excinfo.value)
    assert "details/orphan.md" in message
    assert "not referenced" in message


# -- apply ----------------------------------------------------------------------


def test_apply_creates_month_file_with_heading_and_copies_details(tmp_path):
    bundle = cpl.validate_bundle(make_bundle(tmp_path), DATE)
    checkout = tmp_path / "checkout"

    touched = cpl.apply_bundle(bundle, checkout, LOG_DIR, DATE)

    month_text = (checkout / LOG_DIR / "2026-07.md").read_text()
    assert month_text.startswith(f"# Research log — 2026-07\n\n## {DATE}\n")
    assert month_text.endswith("\n")
    assert not month_text.endswith("\n\n")
    copied = checkout / LOG_DIR / "details" / DETAILS_NAME
    assert copied.read_text() == (bundle.root / "details" / DETAILS_NAME).read_text()
    assert touched == [f"{LOG_DIR}/2026-07.md", f"{LOG_DIR}/details/{DETAILS_NAME}"]


def test_apply_appends_second_entry_after_blank_line(tmp_path):
    bundle = cpl.validate_bundle(make_bundle(tmp_path), DATE)
    checkout = tmp_path / "checkout"
    month_file = checkout / LOG_DIR / "2026-07.md"
    month_file.parent.mkdir(parents=True)
    earlier = "# Research log — 2026-07\n\n## 2026-07-11\n- **Result:** earlier day\n"
    month_file.write_text(earlier)

    cpl.apply_bundle(bundle, checkout, LOG_DIR, DATE)

    month_text = month_file.read_text()
    assert month_text.startswith(earlier.rstrip("\n") + "\n\n" + f"## {DATE}\n")
    assert month_text.endswith("\n")
    assert not month_text.endswith("\n\n")


def test_apply_refuses_to_overwrite_existing_details_file(tmp_path):
    bundle = cpl.validate_bundle(make_bundle(tmp_path), DATE)
    checkout = tmp_path / "checkout"
    dest = checkout / LOG_DIR / "details" / DETAILS_NAME
    dest.parent.mkdir(parents=True)
    dest.write_text("pre-existing\n")

    with pytest.raises(SystemExit) as excinfo:
        cpl.apply_bundle(bundle, checkout, LOG_DIR, DATE)

    assert "refusing to overwrite" in str(excinfo.value)


# -- git/gh orchestration ---------------------------------------------------------


@pytest.fixture
def git_env(monkeypatch):
    """Hermetic git: identity from env, user/system config ignored."""
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test Bot")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "bot@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test Bot")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "bot@example.com")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )
    return result.stdout


@pytest.fixture
def bare_repo(tmp_path, git_env) -> Path:
    """A local bare repo standing in for github.com/husar-robotics/shrek-dog."""
    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    _git("init", "--bare", "-b", "main", str(origin))
    _git("init", "-b", "main", str(seed))
    (seed / "README.md").write_text("# shrek-dog\n")
    _git("add", "README.md", cwd=seed)
    _git("commit", "-m", "init", cwd=seed)
    _git("remote", "add", "origin", str(origin), cwd=seed)
    _git("push", "origin", "main", cwd=seed)
    return origin


def _record_subprocess(monkeypatch):
    """Patch subprocess.run to record every call's argv, passing through to the real thing."""
    calls: list[list[str]] = []
    real_run = subprocess.run

    def recorder(cmd, **kwargs):
        calls.append(list(cmd))
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(cpl.subprocess, "run", recorder)
    return calls


def _mock_pr_endpoint(pr_url: str = f"https://github.com/{REPO}/pull/7"):
    return respx.post(f"https://api.github.com/repos/{REPO}/pulls").mock(
        return_value=httpx.Response(201, json={"html_url": pr_url})
    )


@respx.mock
def test_publish_end_to_end(tmp_path, monkeypatch, bare_repo):
    bundle = cpl.validate_bundle(make_bundle(tmp_path), DATE)
    monkeypatch.setenv("HVSR_TOKEN", "s3cret-token-value")
    calls = _record_subprocess(monkeypatch)
    pr_route = _mock_pr_endpoint()

    pr_url = cpl.publish_bundle(bundle, make_config(), clone_url=str(bare_repo))

    assert pr_url == f"https://github.com/{REPO}/pull/7"

    # The bare repo gained the branch with exactly one commit touching the expected paths.
    branch = f"research-log/{DATE}"
    count = _git("-C", str(bare_repo), "rev-list", "--count", f"main..{branch}")
    assert count.strip() == "1"
    subject = _git("-C", str(bare_repo), "log", "-1", "--format=%s", branch)
    assert subject.strip() == f"research log: {DATE}"
    changed = _git("-C", str(bare_repo), "diff", "--name-only", "main", branch)
    assert sorted(changed.split()) == [
        f"{LOG_DIR}/2026-07.md",
        f"{LOG_DIR}/details/{DETAILS_NAME}",
    ]
    month_blob = _git("-C", str(bare_repo), "show", f"{branch}:{LOG_DIR}/2026-07.md")
    assert f"## {DATE}" in month_blob

    # The PR was opened once, against the default branch, with the right head
    # and the token only in the Authorization header.
    assert pr_route.call_count == 1
    request = pr_route.calls.last.request
    assert request.headers["Authorization"] == "Bearer s3cret-token-value"
    payload = json.loads(request.content)
    assert payload["head"] == branch
    assert payload["base"] == "main"
    assert payload["title"] == f"research log: {DATE}"
    assert f"newsletters/{DATE}.md" in payload["body"]
    assert "Generated with [Claude Code]" in payload["body"]

    # The token value never entered any argv or any URL.
    for cmd in calls:
        assert all("s3cret-token-value" not in str(part) for part in cmd)
    assert "s3cret-token-value" not in str(request.url)


@respx.mock
def test_duplicate_date_refused_and_nothing_pushed(tmp_path, monkeypatch, bare_repo):
    # Seed the origin with a month file that already has the date's section.
    seeded = tmp_path / "seeded"
    _git("clone", str(bare_repo), str(seeded))
    month_file = seeded / LOG_DIR / "2026-07.md"
    month_file.parent.mkdir(parents=True)
    month_file.write_text(f"# Research log — 2026-07\n\n## {DATE}\n- **Result:** already published\n")
    _git("add", ".", cwd=seeded)
    _git("commit", "-m", "prior publish", cwd=seeded)
    _git("push", "origin", "main", cwd=seeded)

    bundle = cpl.validate_bundle(make_bundle(tmp_path), DATE)
    monkeypatch.setenv("HVSR_TOKEN", "s3cret-token-value")
    pr_route = _mock_pr_endpoint()

    with pytest.raises(SystemExit) as excinfo:
        cpl.publish_bundle(bundle, make_config(), clone_url=str(bare_repo))

    message = str(excinfo.value)
    assert f"## {DATE}" in message
    assert "refusing" in message
    branches = _git("-C", str(bare_repo), "for-each-ref", "refs/heads/research-log")
    assert branches.strip() == ""
    assert not pr_route.called


def test_missing_token_is_loud_and_precedes_any_subprocess(tmp_path, monkeypatch):
    bundle = cpl.validate_bundle(make_bundle(tmp_path), DATE)
    monkeypatch.delenv("HVSR_TOKEN", raising=False)
    monkeypatch.setattr(
        cpl.subprocess,
        "run",
        lambda *a, **k: pytest.fail("no subprocess may run before the token check"),
    )

    with pytest.raises(SystemExit) as excinfo:
        cpl.publish_bundle(bundle, make_config())

    assert "HVSR_TOKEN" in str(excinfo.value)


# -- CLI ------------------------------------------------------------------------


def test_dry_run_validates_prints_plan_and_never_runs_git(tmp_path, monkeypatch, capsys):
    bundle_dir = make_bundle(tmp_path)
    config_path = tmp_path / "config.toml"
    config_path.write_text(CONFIG_TOML)
    monkeypatch.setenv("KLAUDIUSZ_CONFIG", str(config_path))
    monkeypatch.delenv("HVSR_TOKEN", raising=False)
    monkeypatch.setattr(
        cpl.subprocess,
        "run",
        lambda *a, **k: pytest.fail("no subprocess may run under --dry-run"),
    )

    exit_code = main(["publish-log", str(bundle_dir), "--date", DATE, "--dry-run"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert REPO in out
    assert f"research-log/{DATE}" in out
    assert f"{LOG_DIR}/2026-07.md" in out
    assert f"{LOG_DIR}/details/{DETAILS_NAME}" in out


def test_bad_date_format_fails_loudly(tmp_path):
    with pytest.raises(SystemExit) as excinfo:
        main(["publish-log", str(tmp_path), "--date", "07/12/2026"])

    assert "YYYY-MM-DD" in str(excinfo.value)


def test_impossible_calendar_date_fails_loudly(tmp_path):
    with pytest.raises(SystemExit) as excinfo:
        main(["publish-log", str(tmp_path), "--date", "2026-02-31"])

    assert "not a real calendar date" in str(excinfo.value)
