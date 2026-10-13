"""Credential resolution in zoho_client._load_credential (2026-10-12): env var > keyring > macOS `security` CLI.

A Homebrew Python upgrade changed the interpreter's code signature, so `keyring` got errSecInteractionNotAllowed
(-25308) from the login keychain while `/usr/bin/security` still read the same item. These tests pin the order,
the fallback, and that a failure never leaks a value into the error text.
"""
from __future__ import annotations

import subprocess
import sys
import types

import pytest

import zoho_client


class _KeyringError(Exception):
    pass


def _fake_keyring(monkeypatch, *, value=None, exc=None):
    mod = types.ModuleType("keyring")

    def get_password(service, account):
        if exc:
            raise exc
        return value

    mod.get_password = get_password
    monkeypatch.setitem(sys.modules, "keyring", mod)


def _fake_security(monkeypatch, *, rc=0, out="s3cret\n", exc=None, calls=None):
    def run(argv, **kw):
        if calls is not None:
            calls.append(argv)
        if exc:
            raise exc
        return subprocess.CompletedProcess(argv, rc, stdout=out, stderr="")

    monkeypatch.setattr(zoho_client.subprocess, "run", run)
    monkeypatch.setattr(zoho_client.sys, "platform", "darwin")
    monkeypatch.setattr(zoho_client.os.path, "exists", lambda p: p == zoho_client.SECURITY_CLI)


@pytest.fixture(autouse=True)
def _no_env(monkeypatch):
    monkeypatch.delenv("ZOHO_CLIENT_ID", raising=False)


def test_env_var_wins(monkeypatch):
    monkeypatch.setenv("ZOHO_CLIENT_ID", "from-env")
    _fake_keyring(monkeypatch, value="from-keyring")
    assert zoho_client._load_credential("CLIENT_ID", "rachel") == "from-env"


def test_keyring_value_used_without_security(monkeypatch):
    calls = []
    _fake_keyring(monkeypatch, value="from-keyring")
    _fake_security(monkeypatch, calls=calls)
    assert zoho_client._load_credential("CLIENT_ID", "rachel") == "from-keyring"
    assert calls == []


def test_keyring_error_falls_back_to_security_cli(monkeypatch):
    calls = []
    _fake_keyring(monkeypatch, exc=_KeyringError("Can't get password from keychain: (-25308, 'Unknown Error')"))
    _fake_security(monkeypatch, calls=calls)
    assert zoho_client._load_credential("CLIENT_ID", "rachel") == "s3cret"
    assert calls == [["/usr/bin/security", "find-generic-password", "-s", "zoho-mail-rachel", "-a", "CLIENT_ID", "-w"]]


def test_keyring_missing_falls_back_to_security_cli(monkeypatch):
    monkeypatch.setitem(sys.modules, "keyring", None)  # import keyring -> ImportError
    _fake_security(monkeypatch)
    assert zoho_client._load_credential("CLIENT_ID", "rachel") == "s3cret"


def test_no_fallback_off_macos(monkeypatch):
    _fake_keyring(monkeypatch, exc=_KeyringError("denied"))
    _fake_security(monkeypatch)
    monkeypatch.setattr(zoho_client.sys, "platform", "win32")
    with pytest.raises(KeyError):
        zoho_client._load_credential("CLIENT_ID", "rachel")


@pytest.mark.parametrize("kw", [{"rc": 44, "out": ""}, {"exc": subprocess.TimeoutExpired("security", 20)},
                                {"exc": OSError("no exec")}, {"rc": 0, "out": "\n"}])
def test_security_failure_raises_keyerror_without_secret(monkeypatch, kw):
    _fake_keyring(monkeypatch, value=None)
    _fake_security(monkeypatch, **kw)
    with pytest.raises(KeyError) as e:
        zoho_client._load_credential("CLIENT_ID", "rachel")
    assert "s3cret" not in str(e.value) and "zoho-mail-rachel" in str(e.value)


def test_no_profile_skips_keychain(monkeypatch):
    calls = []
    _fake_keyring(monkeypatch, value="x")
    _fake_security(monkeypatch, calls=calls)
    with pytest.raises(KeyError):
        zoho_client._load_credential("CLIENT_ID", None)
    assert calls == []
