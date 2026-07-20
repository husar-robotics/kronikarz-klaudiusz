"""Secret hermeticity: every test starts from a "no tokens anywhere" state,
regardless of what the developer's shell exports. Tests that need a token
setenv on top of this fixture. The repo-root .env never leaks in either:
`load_env` runs only at console entry (`cli.run`), and tests drive `main`.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_ambient_tokens(monkeypatch):
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.delenv("DISCORD_READER_TOKEN", raising=False)
    monkeypatch.delenv("HVSR_TOKEN", raising=False)
