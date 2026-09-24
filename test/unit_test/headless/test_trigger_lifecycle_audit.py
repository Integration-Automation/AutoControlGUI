"""Trigger / scheduler / data-source defects from the 2026-09-24 audit.

Two concurrent ``TriggerEngine.start()`` calls made two polling threads and a
``stop()`` during ``start()`` raised; the email watcher's ``stop()`` had the
same race; one malformed email header blocked the mailbox for good; mailbox
names were sent unquoted; a webhook could register a verb the server never
answers; a string ``max_runs`` made a job run on every tick forever; a
corrupt .xlsx escaped the executor as a bare ``BadZipFile``.
"""
import email
import email.policy
import json
import sys
import threading
import time
import types
import zipfile
from email.message import EmailMessage

import pytest

from je_auto_control.utils.data_source import data_source
from je_auto_control.utils.exception.exceptions import AutoControlActionException
from je_auto_control.utils.scheduler import scheduler as sm
from je_auto_control.utils.triggers import email_trigger as et
from je_auto_control.utils.triggers.trigger_engine import FilePathTrigger, TriggerEngine
from je_auto_control.utils.triggers.webhook_server import WebhookTriggerServer

_THREAD_NAMES = ("AutoControlTriggers", "AutoControlEmailTrigger")


@pytest.fixture
def slow_thread_start(monkeypatch):
    """Widen the window between creating the polling thread and starting it."""
    original = threading.Thread.start

    def slow(self):
        if self.name in _THREAD_NAMES:
            time.sleep(0.2)
        return original(self)

    monkeypatch.setattr(threading.Thread, "start", slow)


def _polling_threads(name):
    return sum(thread.name == name and thread.is_alive() for thread in threading.enumerate())


def test_concurrent_starts_make_one_polling_thread(slow_thread_start):
    engine = TriggerEngine(executor=lambda _actions: None)
    before = _polling_threads("AutoControlTriggers")
    starters = [threading.Thread(target=engine.start) for _ in range(2)]
    for starter in starters:
        starter.start()
    for starter in starters:
        starter.join()
    try:
        assert _polling_threads("AutoControlTriggers") - before == 1
    finally:
        engine.stop()


@pytest.mark.parametrize("make", [
    lambda: TriggerEngine(executor=lambda _actions: None),
    lambda: et.EmailTriggerWatcher(executor=lambda *_args: None),
])
def test_stop_during_start_does_not_raise(slow_thread_start, make):
    runner = make()
    starter = threading.Thread(target=runner.start)
    starter.start()
    time.sleep(0.05)
    runner.stop()
    starter.join()
    runner.stop()


def test_file_path_trigger_keeps_its_docstring():
    assert FilePathTrigger.__doc__.startswith("Fire when ``watch_path``")


POISON = b"From: <\"\r\nSubject: bad\r\n\r\nbody\r\n"
GOOD = EmailMessage()
GOOD["From"] = "a@example.com"
GOOD["Subject"] = "good"
GOOD.set_content("body")


class _Imap:
    selected = []

    def __init__(self, *_args, **_kwargs):
        pass

    def login(self, *_args):
        return "OK", [b""]

    def select(self, mailbox, **_kwargs):
        _Imap.selected.append(mailbox)
        return "OK", [b"2"]

    def uid(self, command, *args):
        if command == "SEARCH":
            return "OK", [b"1 2"]
        if command == "FETCH":
            raw = POISON if args[0] == "1" else GOOD.as_bytes()
            return "OK", [(b"x (BODY[] {1}", raw), b")"]
        return "OK", [b""]

    def logout(self):
        pass


@pytest.fixture
def imap(monkeypatch):
    monkeypatch.setattr(et, "default_history_store", types.SimpleNamespace(
        start_run=lambda *a, **k: 1, finish_run=lambda *a, **k: None))
    monkeypatch.setattr(et, "capture_error_snapshot", lambda run_id: None)
    monkeypatch.setattr(et.imaplib, "IMAP4_SSL", _Imap)
    monkeypatch.setattr(et.imaplib, "IMAP4", _Imap)
    _Imap.selected = []


def test_a_malformed_header_neither_blocks_the_mailbox_nor_the_message(tmp_path, imap):
    script = tmp_path / "a.json"
    script.write_text(json.dumps([["AC_noop"]]), encoding="utf-8")
    fired = []
    watcher = et.EmailTriggerWatcher(
        executor=lambda _actions, variables: fired.append(
            (variables["email.subject"], variables["email.from"])))
    watcher.add("imap.example", "u", "pw", str(script), mailbox="Sent Items")
    for _ in range(3):
        watcher.poll_once()
    # How `From: <"` parses differs between CPython patch releases (IndexError
    # on some, "<>" on others); either way both messages fire exactly once.
    assert sorted(subject for subject, _sender in fired) == ["bad", "good"]
    assert _Imap.selected[0] == '"Sent Items"'


class _UnparsableHeaders(EmailMessage):
    """A message whose parsed ``From`` raises, as the email package can."""

    def get(self, name, failobj=None):
        if name == "From":
            raise IndexError("list index out of range")
        return super().get(name, failobj)


def test_an_unparsable_header_falls_back_to_its_raw_text():
    raw = b"From: Alice <a@example.com>\r\nSubject: bad\r\n\r\nbody\r\n"
    msg = email.message_from_bytes(raw, _class=_UnparsableHeaders, policy=email.policy.default)
    payload = et._build_payload("1", msg)
    assert payload["email.from"] == "Alice <a@example.com>"
    assert payload["email.subject"] == "bad"


@pytest.mark.parametrize("name, quoted", [
    ("INBOX", '"INBOX"'), ("[Gmail]/All Mail", '"[Gmail]/All Mail"'),
    ('a"b\\c', '"a\\"b\\\\c"'), ('"Already"', '"Already"'),
])
def test_mailbox_names_are_quoted(name, quoted):
    assert et._quote_mailbox(name) == quoted


def test_a_webhook_verb_the_server_cannot_answer_is_refused():
    server = WebhookTriggerServer()
    with pytest.raises(ValueError, match="HEAD"):
        server.add(path="/h", script_path="x.json", methods=["HEAD"])
    assert server.add(path="/p", script_path="x.json", methods=["patch"]).methods == ("PATCH",)


def test_a_string_max_runs_still_stops_the_job(monkeypatch):
    monkeypatch.setattr(sm, "default_history_store", types.SimpleNamespace(
        start_run=lambda *a, **k: 1, finish_run=lambda *a, **k: None))
    monkeypatch.setattr(sm, "capture_error_snapshot", lambda run_id: None)
    monkeypatch.setattr(sm, "read_executable_action_json", lambda path: [])
    runs = []
    scheduler = sm.Scheduler(executor=lambda _actions: runs.append(1))
    job = scheduler.add_job("x.json", 0.1, max_runs="2")
    assert job.max_runs == 2
    for _ in range(5):
        job.next_run_ts = 0
        scheduler._tick_once()
    assert len(runs) == 2
    assert scheduler.list_jobs() == []


def test_a_corrupt_workbook_is_an_action_error(tmp_path, monkeypatch):
    def load_workbook(**_kwargs):
        raise zipfile.BadZipFile("File is not a zip file")

    monkeypatch.setitem(sys.modules, "openpyxl",
                        types.SimpleNamespace(load_workbook=load_workbook))
    book = tmp_path / "bad.xlsx"
    book.write_bytes(b"not a zip")
    with pytest.raises(AutoControlActionException, match="bad.xlsx"):
        data_source._load_excel({"path": str(book)})
