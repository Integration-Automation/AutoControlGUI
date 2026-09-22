"""Regression tests for the secret-handling defects of the 2026-09-23 audit.

The executor logged every action list and keyed its result record by
``str(action)``, so the passphrase of ``AC_secret_unlock`` and the value of
``AC_secret_set`` reached the log file and every caller of the record; the
socket server logged the raw command text as well. Changing the vault
passphrase deleted the vault and re-added each secret with its own write, and
two config-bundle imports in the same second overwrote the first backup.
"""
import json
import logging

import pytest

from je_auto_control.utils.config_bundle import config_bundle
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.executor.action_executor import Executor
from je_auto_control.utils.executor.action_redaction import redact_actions

_PASSPHRASE = "correct horse battery staple"


# --- redaction ----------------------------------------------------------------

def test_secret_arguments_are_masked_at_any_depth():
    actions = [
        ["AC_secret_unlock", {"passphrase": _PASSPHRASE}],
        ["AC_loop", {"times": 1, "body": [["AC_secret_set", ["NAME", _PASSPHRASE]]]}],
        ["AC_type_keyboard", {"keycode": "a"}],
    ]
    masked = redact_actions(actions)
    assert _PASSPHRASE not in json.dumps(masked)
    assert masked[0] == ["AC_secret_unlock", {"passphrase": "***"}]
    assert masked[2] == actions[2], "other commands keep their arguments"
    assert _PASSPHRASE in json.dumps(actions), "the input is not mutated"


def test_the_executor_neither_logs_nor_records_a_passphrase(caplog):
    executor = Executor()
    executor.event_dict["AC_secret_unlock"] = lambda passphrase: {"unlocked": False}
    with caplog.at_level(logging.INFO, logger="AutoControlGUI"):
        record = executor.execute_action([["AC_secret_unlock", {"passphrase": _PASSPHRASE}]])
    assert _PASSPHRASE not in caplog.text
    assert _PASSPHRASE not in json.dumps(list(record))


def test_a_failing_secret_command_does_not_leak_either(caplog):
    executor = Executor()

    def refuse(passphrase):
        raise ValueError("wrong")

    executor.event_dict["AC_secret_unlock"] = refuse
    with caplog.at_level(logging.INFO, logger="AutoControlGUI"):
        record = executor.execute_action([["AC_secret_unlock", {"passphrase": _PASSPHRASE}]])
    assert _PASSPHRASE not in caplog.text
    assert _PASSPHRASE not in json.dumps(list(record))


def test_the_socket_server_does_not_log_the_command_text(caplog):
    from je_auto_control.utils.socket_server import auto_control_socket_server as server

    class _Request:
        def __init__(self):
            self.chunks = [json.dumps([["AC_secret_unlock", {"passphrase": _PASSPHRASE}]]).encode() + b"\n"]
            self.sent = []

        def settimeout(self, _seconds):
            pass

        def recv(self, _size):
            return self.chunks.pop(0) if self.chunks else b""

        def sendall(self, data):
            self.sent.append(data)

    handler = server.TCPServerHandler.__new__(server.TCPServerHandler)
    handler.request = _Request()
    handler.server = None
    with caplog.at_level(logging.INFO, logger="AutoControlGUI"):
        handler.handle()
    assert _PASSPHRASE not in caplog.text


# --- vault --------------------------------------------------------------------

@pytest.fixture
def vault(tmp_path):
    pytest.importorskip("cryptography")
    from je_auto_control.utils.secrets import secret_store
    manager = secret_store.SecretManager(tmp_path / "vault.json")
    manager.initialize("old")
    manager.set("A", "1")
    manager.set("B", "2")
    return secret_store, manager


def test_changing_the_passphrase_keeps_every_secret(vault):
    _, manager = vault
    manager.change_passphrase("old", "new")
    manager.lock()
    assert manager.unlock("new")
    assert (manager.get("A"), manager.get("B")) == ("1", "2")
    assert not manager.unlock("old")


def test_a_failed_passphrase_change_leaves_the_old_vault(vault, monkeypatch):
    secret_store, manager = vault

    def disk_full(path, payload):
        raise OSError("disk full")

    monkeypatch.setattr(secret_store, "_atomic_write", disk_full)
    with pytest.raises(OSError):
        manager.change_passphrase("old", "new")
    monkeypatch.undo()
    manager.lock()
    assert manager.unlock("old"), "the vault must survive a failed change"
    assert (manager.get("A"), manager.get("B")) == ("1", "2")


def test_vault_errors_are_in_the_framework_family():
    from je_auto_control.utils.secrets.secret_store import SecretStoreError, SecretStoreLocked
    assert issubclass(SecretStoreLocked, AutoControlException)
    assert issubclass(SecretStoreError, RuntimeError)


# --- config bundle ------------------------------------------------------------

def test_backups_in_the_same_second_do_not_overwrite_each_other(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text("original", encoding="utf-8")
    first = config_bundle._unused_backup_path(target, 100)
    target.replace(first)
    target.write_text("second", encoding="utf-8")
    second = config_bundle._unused_backup_path(target, 100)
    assert second != first
    target.replace(second)
    assert first.read_text(encoding="utf-8") == "original"
