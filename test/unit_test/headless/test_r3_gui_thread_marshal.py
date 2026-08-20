"""Round-3 GUI audit regressions for worker-thread -> GUI-thread hand-off.

* ``QTimer.singleShot`` fired from a non-Qt thread never runs (no event loop
  there); the LAN browser, presence roster and WebRTC file-received callbacks
  must marshal via a Qt Signal instead (finding 8);
* the admin-console thumbnail poll must ``deleteLater`` its QThread/worker each
  tick instead of leaking one per interval (finding 9).

Each test drives the real method from a background ``threading.Thread`` and
pumps the GUI event loop, so a queued signal is required for the effect to
appear (a thread-affine ``singleShot`` would not fire).

Three of these run in a subprocess. Constructing the WebRTC panel or the
admin console, then tearing a worker QThread down, aborts the *shared* pytest
process under offscreen Qt (``0xC0000409`` / SIGABRT) — and because
``deleteLater`` is a no-op until an event loop runs, the abort lands inside
some later, unrelated test file. They were skipped outright for that reason;
quarantining the Qt lifetime in a child process is what
``test_actions_menu_gui`` already does, and it is what they needed. The child
writes a JSON verdict per check and ``os._exit(0)``s without teardown.
"""
import json
import os
import pathlib
import subprocess
import sys
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtWidgets import QApplication  # noqa: E402


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _pump_until(qapp, predicate, timeout=3.0):
    deadline = time.time() + timeout
    while not predicate() and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.005)
    return predicate()


def _run_off_thread(target):
    thread = threading.Thread(target=target)
    thread.start()
    thread.join(3.0)


# --- Finding 8: LAN browse dialog ------------------------------------------

def test_lan_browse_services_marshaled_to_gui(qapp, monkeypatch):
    import je_auto_control.utils.remote_desktop.lan_discovery as lan
    # Keep the dialog hermetic: no real mDNS browser.
    monkeypatch.setattr(lan, "is_discovery_available", lambda: False)
    from je_auto_control.gui.remote_desktop.webrtc_dialogs import LanBrowseDialog

    dialog = LanBrowseDialog()
    try:
        assert dialog._table.rowCount() == 0
        services = {"h1": {"host_id": "h1", "ip": "10.0.0.1",
                           "signaling_url": "wss://x", "name": "Host One"}}
        _run_off_thread(lambda: dialog._update_services(services))
        assert _pump_until(qapp, lambda: dialog._table.rowCount() == 1)
    finally:
        dialog.close()
        dialog.deleteLater()


# --- Finding 8: presence roster --------------------------------------------

def test_presence_registry_event_marshaled_to_gui(qapp):
    from je_auto_control.gui.presence_tab import PresenceTab

    tab = PresenceTab()
    try:
        tab._timer.stop()  # only the marshaled signal may refresh the roster
        tab._status.setText("SENTINEL")
        _run_off_thread(lambda: tab._on_registry_event("viewer-x", None))
        assert _pump_until(qapp, lambda: tab._status.text() != "SENTINEL")
    finally:
        tab._timer.stop()
        tab._registry.remove_listener(tab._on_registry_event)
        tab.deleteLater()


# --- The three that need their own process --------------------------------

# Each check returns "ok", "failed: ...", or "unavailable: ..." so a missing
# optional extra reads as a skip rather than a failure: CI's pytest-headless
# does not install [webrtc], and importing the panel without it raises.
_PROBE = r"""
import json
import os
import pathlib
import sys
import tempfile
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import shiboken6
from PySide6.QtCore import QEvent, QObject, QThread
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
report = {}


def pump_until(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    return predicate()


def run_off_thread(target):
    thread = threading.Thread(target=target)
    thread.start()
    thread.join(3.0)


def check_panel_signals():
    from je_auto_control.gui.remote_desktop.webrtc_panel import _PanelSignals
    assert hasattr(_PanelSignals(), "file_received"), "no file_received signal"


def check_webrtc_marshal():
    import types
    from je_auto_control.gui.remote_desktop.webrtc_panel import (
        _PanelSignals, _WebRTCViewerPanel,
    )

    signals = _PanelSignals()

    class Receiver(QObject):
        def __init__(self):
            super().__init__()
            self.got = None

        def on_file(self, path):
            self.got = path

    receiver = Receiver()
    signals.file_received.connect(receiver.on_file)
    stub = types.SimpleNamespace(_signals=signals)

    run_off_thread(
        lambda: _WebRTCViewerPanel._on_received_file(stub, "file-123"))
    assert pump_until(lambda: receiver.got == "file-123"), (
        "the file-received callback never reached the GUI thread; a "
        "thread-affine QTimer.singleShot would fail exactly like this")


def check_thumbnail_reaped():
    import je_auto_control.gui.admin_console_tab as admin_mod
    from je_auto_control.utils.admin.admin_client import AdminConsoleClient

    tmp = pathlib.Path(tempfile.mkdtemp())
    client = AdminConsoleClient(persist_path=tmp / "hosts.json")
    admin_mod.default_admin_console = lambda: client
    # Don't run a real background thread: the reaping wiring is what matters,
    # and this keeps the check deterministic (no timing, no dangling threads).
    admin_mod.QThread.start = lambda self: None

    tab = admin_mod.AdminConsoleTab()
    tab._thumb_timer.stop()
    tab._refresh_thumbnails()

    thread = tab._thumb_thread
    assert thread is not None, "no thumbnail QThread was created"
    assert thread in tab.findChildren(QThread), "thread is not a child of the tab"

    thread.finished.emit()  # simulate the QThread finishing
    assert tab._thumb_thread is None, "_on_thumb_thread_done did not run"
    # Flush the deferred deletions the finished signal scheduled.
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    # Without the deleteLater wiring the QThread would linger as a child of
    # the tab, accumulating one per poll tick.
    assert not shiboken6.Shiboken.isValid(thread), "the QThread outlived finish"
    assert tab.findChildren(QThread) == [], "a QThread lingers as a child"


for name, check in [
    ("panel_signals", check_panel_signals),
    ("webrtc_marshal", check_webrtc_marshal),
    ("thumbnail_reaped", check_thumbnail_reaped),
]:
    try:
        check()
    except ImportError as error:
        report[name] = "unavailable: %s" % (error,)
    except AssertionError as error:
        report[name] = "failed: %s" % (error or "assertion failed",)
    except BaseException as error:
        report[name] = "error: %s: %s" % (type(error).__name__, error)
    else:
        report[name] = "ok"

sys.stdout.write(json.dumps(report))
sys.stdout.flush()
# Skip Qt/native-thread teardown entirely -- that teardown is the whole
# reason this runs out of process. The report is already on stdout.
os._exit(0)
"""


@pytest.fixture(scope="module")
def marshal_report():
    """Run all three checks in one child process; return its verdicts."""
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    # argv is this interpreter plus a module-level literal probe. No shell.
    completed = subprocess.run(  # nosec B603  # nosemgrep  # reason: literal argv, no shell
        [sys.executable, "-c", _PROBE],
        capture_output=True, text=True, check=False, timeout=180, env=env,
    )
    if completed.returncode != 0 or not completed.stdout:
        pytest.fail(
            "thread-marshal probe subprocess failed "
            f"(exit {completed.returncode}):\n{completed.stdout}\n{completed.stderr}"
        )
    return json.loads(completed.stdout)


def _verdict(report, key):
    """Turn one probe verdict into a pass, a skip or a named failure."""
    status = report.get(key)
    assert status is not None, f"{key} missing from the probe report: {report}"
    if status.startswith("unavailable:"):
        pytest.skip(status)
    assert status == "ok", status


def test_panel_signals_expose_file_received(marshal_report):
    """The panel declares the signal the worker hands the file back on."""
    _verdict(marshal_report, "panel_signals")


def test_webrtc_received_file_marshaled_to_gui(marshal_report):
    """A file received off-thread reaches the GUI thread via a queued signal."""
    _verdict(marshal_report, "webrtc_marshal")


def test_thumbnail_poll_thread_is_reaped(marshal_report):
    """The thumbnail poll deletes its QThread per tick instead of leaking one."""
    _verdict(marshal_report, "thumbnail_reaped")
