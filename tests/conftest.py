"""Keychain hermeticity: no test may ever read or write the developer's real
OS keychain, and every test starts from a "no tokens anywhere" state. Tests
that need a token layer setenv/setattr on top of this fixture."""

from __future__ import annotations

import pytest

from klaudiusz import config as config_module


def _forbid(*args, **kwargs):
    raise AssertionError(
        "test touched the real OS keychain; monkeypatch config_module._keyring_* explicitly"
    )


@pytest.fixture(autouse=True)
def _no_real_keychain(monkeypatch):
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.delenv("DISCORD_READER_TOKEN", raising=False)
    monkeypatch.setattr(config_module, "_keyring_get", lambda entry: None)
    monkeypatch.setattr(config_module, "_keyring_set", _forbid)
    monkeypatch.setattr(config_module, "_keyring_delete", _forbid)
