from __future__ import annotations

from klaudiusz.cli import main


def test_version_returns_zero_and_prints_version(capsys):
    exit_code = main(["version"])

    assert exit_code == 0
    out = capsys.readouterr().out.strip()
    assert out
