"""Email-trigger defects from the 2026-09-24 audit.

A script error outside a narrow tuple (``KeyError``, ``TypeError``) skipped
marking the message seen, so it re-fired on every poll and was recorded as
OK; the IMAP connection had no timeout; and a body in a charset Python does
not know was dropped.
"""
import json
import types
from email.message import EmailMessage

import pytest

from je_auto_control.utils.triggers import email_trigger as et

RAW = EmailMessage()
RAW["From"] = "a@example.com"
RAW["Subject"] = "hi"
RAW.set_content("body")


class _Imap:
    stores = []

    def __init__(self, *_args, **kwargs):
        self.timeout = kwargs.get("timeout")

    def login(self, *_args):
        return "OK", [b""]

    def select(self, *_args, **_kwargs):
        return "OK", [b"1"]

    def response(self, code):
        return code, [b"1"] if code == "UIDVALIDITY" else [None]

    def uid(self, command, *args):
        if command == "SEARCH":
            return "OK", [b"7"]
        if command == "FETCH":
            return "OK", [(b"7 (BODY[] {1}", RAW.as_bytes()), b")"]
        if command == "STORE":
            _Imap.stores.append(args)
        return "OK", [b""]

    def logout(self):
        pass


@pytest.fixture
def history(monkeypatch):
    runs = []
    monkeypatch.setattr(et, "default_history_store", types.SimpleNamespace(
        start_run=lambda *a, **k: len(runs),
        finish_run=lambda run_id, status, error, **k: runs.append((status, error))))
    monkeypatch.setattr(et, "capture_error_snapshot", lambda run_id: None)
    monkeypatch.setattr(et.imaplib, "IMAP4_SSL", _Imap)
    monkeypatch.setattr(et.imaplib, "IMAP4", _Imap)
    _Imap.stores = []
    return runs


def test_a_failing_script_fires_once_and_is_recorded_as_an_error(tmp_path, history):
    script = tmp_path / "a.json"
    script.write_text(json.dumps([["AC_noop"]]), encoding="utf-8")
    calls = []

    def executor(_actions, variables):
        calls.append(variables["email.uid"])
        raise KeyError("email.missing")

    watcher = et.EmailTriggerWatcher(executor=executor)
    trigger = watcher.add("imap.example", "u", "pw", str(script), mark_seen=True)
    for _ in range(3):
        watcher.poll_once()
    assert calls == ["7"]
    assert "7" in trigger._seen_uids
    assert len(_Imap.stores) == 1
    assert [status for status, _error in history] == [et.STATUS_ERROR]


@pytest.mark.parametrize("use_ssl", [True, False])
def test_the_imap_connection_is_bounded(history, use_ssl):
    trigger = types.SimpleNamespace(host="h", port=1, use_ssl=use_ssl,
                                    username="u", password="p")
    assert et._connect(trigger).timeout == et._IMAP_TIMEOUT_S


def test_a_body_in_an_unknown_charset_is_kept():
    message = et.email.message_from_bytes(
        b"Content-Type: text/plain; charset=unknown-8bit\r\n\r\nhello world\r\n",
        policy=et.email.policy.default)
    assert et._extract_text_body(message) == "hello world"
