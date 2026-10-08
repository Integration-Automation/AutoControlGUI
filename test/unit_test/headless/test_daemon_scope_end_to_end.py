"""Every daemon really fires its script in a variable scope of its own.

U-20261009-07 isolated scheduler jobs, triggers, hotkeys, webhooks and e-mail
triggers by wrapping their shared helper, and tested the helper. Here each
engine is driven for real -- its own thread, its own poll loop, its own HTTP
handler -- and three scripts are fired through it in turn:

1. one that sets ``${user}``,
2. one that only reads ``${user}`` (it must fail: nothing set it in *this*
   run), and
3. one that sets and then reads it (it must succeed, which shows the probe
   works on that engine's thread and step 2 was not vacuous).

Fakes stand in for everything outside the engine: the run-history store, the
error snapshot, the OS hotkey listener and the IMAP server. The webhook is
posted over loopback to a port the OS picks. The only commands that run are
variable commands and a probe, so no input reaches the desktop.
"""
import json
import queue
import threading
import time
import urllib.request
from email.message import EmailMessage

import pytest

from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.run_history.history_store import STATUS_ERROR, STATUS_OK

PROBE = "AC_scope_probe"
_SET_USER = ["AC_set_var", {"name": "user", "value": "alice"}]
_READ_USER = [PROBE, {"value": "${user}"}]
_WAIT_S = 10.0


class _History:
    """A run-history store that keeps finished runs in memory and signals them."""

    def __init__(self):
        self._cond = threading.Condition()
        self._next_id = 0
        self.finished = []

    def start_run(self, _source, _target, _script_path):
        with self._cond:
            self._next_id += 1
            return self._next_id

    def finish_run(self, _run_id, status, error_text=None, artifact_path=None):
        with self._cond:
            self.finished.append((status, error_text))
            self._cond.notify_all()

    def wait_finished(self, count):
        """Block until ``count`` runs have finished; return their statuses."""
        with self._cond:
            if not self._cond.wait_for(lambda: len(self.finished) >= count, _WAIT_S):
                raise AssertionError(f"{len(self.finished)} run(s) finished, wanted {count}")
            return [status for status, _error in self.finished]


@pytest.fixture
def seen():
    """Register a probe command on the module executor; restore it afterwards."""
    values = []
    saved = executor.variables.as_dict()
    executor.variables.clear()
    executor.event_dict[PROBE] = lambda value=None: values.append(value) or value
    yield values
    executor.event_dict.pop(PROBE, None)
    executor.variables.clear()
    executor.variables.update_many(saved)


@pytest.fixture
def scripts(tmp_path):
    """The three action files, by name."""
    paths = {}
    for name, actions in (("set", [_SET_USER]), ("read", [_READ_USER]),
                          ("both", [_SET_USER, _READ_USER])):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(actions), encoding="utf-8")
        paths[name] = str(path)
    return paths


def _fake_history(monkeypatch, module) -> _History:
    """Give ``module`` an in-memory history and no error snapshot."""
    history = _History()
    monkeypatch.setattr(module, "default_history_store", history)
    monkeypatch.setattr(module, "capture_error_snapshot", lambda _run_id: None)
    return history


def _until(predicate) -> None:
    deadline = time.monotonic() + _WAIT_S
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not reached")
        time.sleep(0.01)


def _assert_isolated(history: _History, seen: list) -> None:
    """Three runs finished: set ok, read failed, set-then-read ok."""
    statuses = history.wait_finished(3)
    assert statuses == [STATUS_OK, STATUS_ERROR, STATUS_OK]
    assert "action(s) failed" in history.finished[1][1]
    assert seen == ["alice"]            # only the third run's own value
    assert "user" not in executor.variables


def test_scheduler_jobs_do_not_share_variables(monkeypatch, seen, scripts):
    from je_auto_control.utils.scheduler import scheduler as scheduler_module
    history = _fake_history(monkeypatch, scheduler_module)
    scheduler = scheduler_module.Scheduler(tick_seconds=0.1)
    scheduler.start()
    try:
        for count, name in enumerate(("set", "read", "both"), start=1):
            scheduler.add_job(scripts[name], 0.1, repeat=False)
            history.wait_finished(count)
    finally:
        scheduler.stop()
    _assert_isolated(history, seen)


def test_triggers_do_not_share_variables(monkeypatch, seen, scripts, tmp_path):
    from je_auto_control.utils.triggers import trigger_engine
    history = _fake_history(monkeypatch, trigger_engine)
    engine = trigger_engine.TriggerEngine(tick_seconds=0.05)
    engine.start()
    try:
        for count, name in enumerate(("set", "read", "both"), start=1):
            watched = tmp_path / f"{name}.flag"
            trigger = engine.add(trigger_engine.FilePathTrigger(
                trigger_id=name, script_path=scripts[name],
                watch_path=str(watched), cooldown_seconds=0.0))
            _until(lambda: trigger._primed)  # noqa: SLF001, B023  # reason: the first poll only records a baseline
            watched.write_text("x", encoding="utf-8")
            history.wait_finished(count)
    finally:
        engine.stop()
    _assert_isolated(history, seen)


class _FakeHotkeyBackend:
    """Stands in for the OS listener: the test says which binding was pressed."""

    name = "fake"

    def __init__(self):
        self.pressed = queue.Queue()

    def run_forever(self, context) -> None:
        while not context.stop_event.is_set():
            try:
                binding_id = self.pressed.get(timeout=0.05)
            except queue.Empty:
                continue
            context.fire(binding_id)


def test_hotkey_bindings_do_not_share_variables(monkeypatch, seen, scripts):
    from je_auto_control.utils.hotkey import backends, hotkey_daemon
    history = _fake_history(monkeypatch, hotkey_daemon)
    backend = _FakeHotkeyBackend()
    monkeypatch.setattr(backends, "get_backend", lambda: backend)
    daemon = hotkey_daemon.HotkeyDaemon()
    bindings = {name: daemon.bind(f"ctrl+alt+f{number}", scripts[name])
                for number, name in ((7, "set"), (8, "read"), (9, "both"))}
    daemon.start()
    try:
        for count, name in enumerate(("set", "read", "both"), start=1):
            backend.pressed.put(bindings[name].binding_id)
            history.wait_finished(count)
    finally:
        daemon.stop()
    _assert_isolated(history, seen)
    assert [binding.fired for binding in bindings.values()] == [1, 1, 1]


def _post(port: int, path: str, body: dict) -> dict:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=_WAIT_S) as reply:  # nosec B310  # reason: loopback, fixed scheme
        return json.loads(reply.read())


def test_webhooks_do_not_share_variables(monkeypatch, seen, scripts, tmp_path):
    from je_auto_control.utils.triggers import webhook_server
    history = _fake_history(monkeypatch, webhook_server)
    echo = tmp_path / "echo.json"
    echo.write_text(json.dumps([[PROBE, {"value": "${webhook.path}"}]]), encoding="utf-8")
    server = webhook_server.WebhookTriggerServer()
    for name in ("set", "read", "both"):
        server.add(f"/{name}", scripts[name])
    server.add("/echo", str(echo))
    _host, port = server.start("127.0.0.1", 0)
    try:
        for name in ("set", "read", "both"):
            assert _post(port, f"/{name}", {"user": "from-the-body"})["fired"] is True
        _assert_isolated(history, seen)
        # The payload is seeded into that firing's scope and nowhere else.
        _post(port, "/echo", {})
        assert seen == ["alice", "/echo"]
        assert "webhook.path" not in executor.variables
    finally:
        server.stop()


class _FakeImap:
    """An IMAP server with one unread message, whatever the mailbox."""

    def __init__(self, host, port, ssl_context=None, timeout=None):
        self.host = host

    def login(self, _user, _password):
        return ("OK", [b"logged in"])

    def select(self, _mailbox, readonly=False):
        return ("OK", [b"1"])

    def response(self, code):
        return (code, [b"1"] if code == "UIDVALIDITY" else [None])

    def uid(self, command, *_args):
        if command == "SEARCH":
            return ("OK", [b"1"])
        if command == "FETCH":
            message = EmailMessage()
            message["Subject"] = f"hello {self.host}"
            message["From"] = "sender@example.com"
            message.set_content("body")
            raw = message.as_bytes()
            return ("OK", [(b"1 (BODY[] {%d}" % len(raw), raw)])
        return ("OK", [b"stored"])

    def logout(self):
        return ("BYE", [b"bye"])


def test_email_triggers_do_not_share_variables(monkeypatch, seen, scripts, tmp_path):
    from je_auto_control.utils.triggers import email_trigger
    history = _fake_history(monkeypatch, email_trigger)
    monkeypatch.setattr(email_trigger.imaplib, "IMAP4_SSL", _FakeImap)
    monkeypatch.setattr(email_trigger.imaplib, "IMAP4", _FakeImap)
    subject = tmp_path / "subject.json"
    subject.write_text(json.dumps([[PROBE, {"value": "${email.subject}"}]]), encoding="utf-8")
    watcher = email_trigger.EmailTriggerWatcher()
    for name in ("set", "read", "both"):
        watcher.add(f"{name}.example.com", "u", "p", scripts[name])
        # One pass per trigger: its one message fires, the earlier triggers'
        # messages are already seen.
        assert watcher.poll_once() == 1
    _assert_isolated(history, seen)
    watcher.add("subject.example.com", "u", "p", str(subject))
    assert watcher.poll_once() == 1
    assert seen == ["alice", "hello subject.example.com"]
    assert "email.subject" not in executor.variables
