"""Tests for the IMAP poll email trigger."""
from email.message import EmailMessage
from typing import List

import pytest

from je_auto_control.utils.triggers import email_trigger as et


class _FakeIMAP:
    """Minimal in-memory IMAP stub matching the subset our code uses."""

    instances: List["_FakeIMAP"] = []

    def __init__(self, host: str, port: int, ssl_context=None):
        self.host = host
        self.port = port
        self.ssl_context = ssl_context
        self.logged_in = False
        self.selected = None
        self.searches: List[str] = []
        self.fetched: List[bytes] = []
        self.flagged: List[bytes] = []
        self.logged_out = False
        self._uids = list(self.next_uids)
        self._messages = dict(self.next_messages)
        _FakeIMAP.instances.append(self)

    next_uids: List[bytes] = []
    next_messages: dict = {}

    def login(self, user, password):
        self.logged_in = True
        return ("OK", [b"logged in"])

    def select(self, mailbox, readonly=False):
        self.selected = (mailbox, readonly)
        return ("OK", [b"1"])

    def uid(self, command, *args):
        if command == "SEARCH":
            criteria = args[1]
            self.searches.append(criteria)
            return ("OK", [b" ".join(self._uids)])
        if command == "FETCH":
            uid = args[0]
            self.fetched.append(uid)
            payload = self._messages.get(uid)
            if payload is None:
                return ("NO", [None])
            return ("OK", [(b"1 (RFC822 {%d}" % len(payload), payload)])
        if command == "STORE":
            self.flagged.append(args[0])
            return ("OK", [b"stored"])
        return ("NO", [None])

    def logout(self):
        self.logged_out = True


@pytest.fixture(autouse=True)
def imap_stub(monkeypatch):
    _FakeIMAP.instances = []
    monkeypatch.setattr(et.imaplib, "IMAP4_SSL", _FakeIMAP)
    monkeypatch.setattr(et.imaplib, "IMAP4", _FakeIMAP)
    yield


def _build_message(subject: str, sender: str, body: str) -> bytes:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = "user@example.com"
    msg["Message-ID"] = "<abc-123@example.com>"
    msg.set_content(body)
    return msg.as_bytes()


@pytest.fixture
def watcher():
    captured = []

    def fake_executor(actions, variables):
        captured.append((actions, dict(variables)))

    w = et.EmailTriggerWatcher(executor=fake_executor)
    w.captured = captured  # type: ignore[attr-defined]
    yield w
    w.stop()


def test_add_validates_required_fields(watcher):
    with pytest.raises(ValueError):
        watcher.add(host="", username="u", password="p", script_path="x")


def test_add_default_port_for_ssl(watcher):
    trigger = watcher.add(host="imap.example.com", username="u",
                          password="p", script_path="s.json")
    assert trigger.port == 993
    assert trigger.use_ssl is True


def test_add_default_port_for_plain(watcher):
    trigger = watcher.add(host="imap.example.com", username="u",
                          password="p", script_path="s.json", use_ssl=False)
    assert trigger.port == 143


def test_poll_once_returns_zero_when_no_messages(watcher, tmp_path):
    script = tmp_path / "s.json"
    script.write_text('[["AC_screen_size"]]', encoding="utf-8")
    watcher.add(host="imap.example.com", username="u", password="p",
                script_path=str(script))
    _FakeIMAP.next_uids = []
    _FakeIMAP.next_messages = {}
    assert watcher.poll_once() == 0


def test_poll_once_fires_on_matching_message(watcher, tmp_path):
    script = tmp_path / "s.json"
    script.write_text('[["AC_screen_size"]]', encoding="utf-8")
    trigger = watcher.add(
        host="imap.example.com", username="u", password="p",
        script_path=str(script),
    )
    raw = _build_message("Build OK", "ci@example.com", "everything green")
    _FakeIMAP.next_uids = [b"42"]
    _FakeIMAP.next_messages = {b"42": raw}

    fired = watcher.poll_once()

    assert fired == 1
    assert len(watcher.captured) == 1  # type: ignore[attr-defined]
    actions, variables = watcher.captured[0]  # type: ignore[attr-defined]
    assert actions == [["AC_screen_size"]]
    assert variables["email.subject"] == "Build OK"
    assert variables["email.from"] == "ci@example.com"
    assert "everything green" in variables["email.body"]
    assert variables["email.uid"] == "42"
    assert trigger.fired == 1


def test_mark_seen_flag_is_sent(watcher, tmp_path):
    script = tmp_path / "s.json"
    script.write_text('[["AC_screen_size"]]', encoding="utf-8")
    watcher.add(host="imap.example.com", username="u", password="p",
                script_path=str(script))
    _FakeIMAP.next_uids = [b"7"]
    _FakeIMAP.next_messages = {b"7": _build_message("hi", "a@b.c", "body")}
    watcher.poll_once()
    inst = _FakeIMAP.instances[-1]
    assert inst.flagged == [b"7"]


def test_mark_seen_disabled_skips_flag(watcher, tmp_path):
    script = tmp_path / "s.json"
    script.write_text('[["AC_screen_size"]]', encoding="utf-8")
    watcher.add(host="imap.example.com", username="u", password="p",
                script_path=str(script), mark_seen=False)
    _FakeIMAP.next_uids = [b"7"]
    _FakeIMAP.next_messages = {b"7": _build_message("hi", "a@b.c", "body")}
    watcher.poll_once()
    inst = _FakeIMAP.instances[-1]
    assert inst.flagged == []


def test_uid_not_double_fired(watcher, tmp_path):
    script = tmp_path / "s.json"
    script.write_text('[["AC_screen_size"]]', encoding="utf-8")
    watcher.add(host="imap.example.com", username="u", password="p",
                script_path=str(script))
    raw = _build_message("once", "a@b.c", "hello")
    _FakeIMAP.next_uids = [b"7"]
    _FakeIMAP.next_messages = {b"7": raw}
    assert watcher.poll_once() == 1
    assert watcher.poll_once() == 0


def test_disabled_trigger_does_not_poll(watcher, tmp_path):
    script = tmp_path / "s.json"
    script.write_text('[["AC_screen_size"]]', encoding="utf-8")
    trigger = watcher.add(host="imap.example.com", username="u",
                          password="p", script_path=str(script))
    watcher.set_enabled(trigger.trigger_id, False)
    _FakeIMAP.next_uids = [b"99"]
    _FakeIMAP.next_messages = {
        b"99": _build_message("ignored", "a@b.c", "x"),
    }
    assert watcher.poll_once() == 0


def test_remove_returns_false_for_unknown(watcher):
    assert watcher.remove("nope") is False


def test_decode_header_handles_encoded_words():
    assert "ñ" in et._decode_header_value("=?utf-8?b?w7E=?=")
