"""Regression tests for the action-signing / encryption defects of the 2026-09-23 audit.

``JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS`` was checked by ``execute_files`` only:
the CLI, the scheduler, triggers, hotkeys, webhooks and the MCP run tool ran
unsigned files, and even ``execute_files`` verified one read of the file and
parsed another. Key files were written and then chmod-ed, an empty key file was
accepted as an empty HMAC key, and a passphrase became a Fernet key through one
unsalted SHA-256.
"""
import json
import os
import stat
import sys
from pathlib import Path

import pytest

from je_auto_control.utils.action_signing import signer
from je_auto_control.utils.action_signing._key_file import load_or_create_key_file
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.json import json_file

_KEY = b"k" * 32


@pytest.fixture
def enforced(monkeypatch):
    monkeypatch.setenv("JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS", "1")


def _script(tmp_path, actions=None):
    path = tmp_path / "flow.json"
    path.write_text(json.dumps(actions or [["AC_noop"]]), encoding="utf-8")
    return path


# --- one loader for every execution path ------------------------------------

def test_an_unsigned_file_is_refused_when_enforced(tmp_path, enforced):
    with pytest.raises(AutoControlException, match="missing signature"):
        json_file.read_executable_action_json(str(_script(tmp_path)))


def test_a_signed_file_loads_when_enforced(tmp_path, enforced, monkeypatch):
    path = _script(tmp_path)
    signer.sign_action_file(path, _KEY)
    monkeypatch.setattr(signer, "_load_or_create_key", lambda key: _KEY)
    assert json_file.read_executable_action_json(str(path)) == [["AC_noop"]]


def test_the_verified_bytes_are_the_parsed_bytes(tmp_path, enforced, monkeypatch):
    path = _script(tmp_path)
    signer.sign_action_file(path, _KEY)
    monkeypatch.setattr(signer, "_load_or_create_key", lambda key: _KEY)
    reads = []
    real_read_bytes = type(path).read_bytes

    def counting_read_bytes(self):
        reads.append(self.name)
        return real_read_bytes(self)

    monkeypatch.setattr(type(path), "read_bytes", counting_read_bytes)
    json_file.read_executable_action_json(str(path))
    assert reads.count("flow.json") == 1, "verify and parse must share one read"


def test_nothing_changes_when_not_enforced(tmp_path, monkeypatch):
    monkeypatch.delenv("JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS", raising=False)
    assert json_file.read_executable_action_json(str(_script(tmp_path))) == [["AC_noop"]]


@pytest.mark.parametrize("module_name", [
    "je_auto_control.utils.scheduler.scheduler",
    "je_auto_control.utils.triggers.trigger_engine",
    "je_auto_control.utils.triggers.email_trigger",
    "je_auto_control.utils.triggers.webhook_server",
    "je_auto_control.utils.hotkey.hotkey_daemon",
])
def test_background_runners_load_through_the_verifying_reader(module_name):
    module = __import__(module_name, fromlist=["_"])
    assert module.read_executable_action_json is json_file.read_executable_action_json
    assert not hasattr(module, "read_action_json")


def test_the_cli_run_command_refuses_an_unsigned_file(tmp_path, enforced, capsys):
    from je_auto_control import cli
    assert cli.main(["run", str(_script(tmp_path))]) != 0
    assert "missing signature" in capsys.readouterr().err


def test_the_mcp_run_tool_refuses_an_unsigned_file(tmp_path, enforced):
    from je_auto_control.utils.mcp_server.tools import _handlers_runs
    with pytest.raises(AutoControlException, match="missing signature"):
        _handlers_runs.execute_action_file(str(_script(tmp_path)))


# --- key files ----------------------------------------------------------------

def test_a_short_key_file_is_refused(tmp_path):
    path = tmp_path / "key"
    path.write_bytes(b"")
    with pytest.raises(AutoControlException, match="fewer than 32"):
        load_or_create_key_file(path, lambda: b"x" * 32, 32)


def test_a_new_key_file_is_created_private(tmp_path):
    path = tmp_path / "sub" / "key"
    assert load_or_create_key_file(path, lambda: b"x" * 32, 32) == b"x" * 32
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_an_existing_key_file_is_never_overwritten(tmp_path):
    path = tmp_path / "key"
    path.write_bytes(b"y" * 32)
    assert load_or_create_key_file(path, lambda: b"x" * 32, 32) == b"y" * 32


def test_an_empty_explicit_signing_key_is_refused(tmp_path):
    with pytest.raises(AutoControlException, match="empty"):
        signer.sign_action_file(_script(tmp_path), b"")


# --- passphrase encryption ----------------------------------------------------

@pytest.fixture
def cipher():
    pytest.importorskip("cryptography")
    from je_auto_control.utils.action_signing import cipher as module
    return module


def test_passphrase_encryption_is_salted(tmp_path, cipher):
    path = _script(tmp_path)
    first = Path(cipher.encrypt_action_file(path, "pw")).read_bytes()
    second = Path(cipher.encrypt_action_file(path, "pw")).read_bytes()
    assert first.startswith(b"ACENC1:")
    salt = slice(len(b"ACENC1:"), len(b"ACENC1:") + 16)
    assert first[salt] != second[salt]
    enc = tmp_path / "a.enc"
    enc.write_bytes(first)
    out = cipher.decrypt_action_file(enc, "pw", output_path=tmp_path / "out.json")
    assert json.loads(Path(out).read_text(encoding="utf-8")) == [["AC_noop"]]


def test_a_wrong_passphrase_is_refused(tmp_path, cipher):
    enc = cipher.encrypt_action_file(_script(tmp_path), "pw")
    with pytest.raises(AutoControlException, match="wrong key"):
        cipher.decrypt_action_file(enc, "other", output_path=tmp_path / "o.json")


def test_files_from_before_the_salt_still_decrypt(tmp_path, cipher):
    from cryptography.fernet import Fernet
    legacy = Fernet(cipher._legacy_key(b"pw")).encrypt(b'[["AC_noop"]]')
    enc = tmp_path / "old.json.enc"
    enc.write_bytes(legacy)
    out = cipher.decrypt_action_file(enc, "pw")
    assert Path(out).read_text(encoding="utf-8") == '[["AC_noop"]]'
