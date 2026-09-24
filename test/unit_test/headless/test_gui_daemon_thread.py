"""Remote-desktop workers survive their owner and interpreter exit (offscreen).

The WebRTC signaling workers and the viewer's file-send thread were
``QThread`` subclasses: exiting while one sat in a signaling long-poll, or
closing the panel that owned a transfer, destroyed a running ``QThread``,
which aborts the process. They are ``DaemonThread``s now.
"""
import os
import subprocess  # nosec B404  # reason: runs this test's own probe script
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

_REPO_ROOT = Path(__file__).resolve().parents[3]

_PROBE = textwrap.dedent("""
    import os, sys, time
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication, QWidget
    from je_auto_control.gui.remote_desktop import webrtc_workers
    from je_auto_control.utils.remote_desktop import signaling_client

    def slow_poll(*args, **kwargs):
        time.sleep(60)          # a signaling long-poll that outlives everything
        return "answer"

    signaling_client.push_offer = lambda *a, **k: None
    signaling_client.wait_for_answer = slow_poll
    app = QApplication([])
    owner = QWidget()
    worker = webrtc_workers.HostSignalingWorker(
        server_url="http://127.0.0.1:1", host_id="h", secret=None,
        offer_sdp="sdp", parent=owner)
    worker.start()
    time.sleep(0.2)
    if sys.argv[1] == "owner":
        owner.deleteLater()
        del owner, worker
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        app.processEvents()
        print("owner gone")
    print("exiting")
""")


def _run_probe(mode: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT))
    argv = [sys.executable, "-c", _PROBE, mode]   # a literal probe; these tests set mode
    return subprocess.run(argv, env=env, timeout=60,  # nosec B603  # nosemgrep  # reason: literal argv
                          capture_output=True, text=True, check=False)


@pytest.mark.parametrize("mode", ["exit", "owner"])
def test_a_worker_in_a_long_poll_neither_aborts_nor_holds_up_exit(mode):
    started = time.monotonic()
    done = _run_probe(mode)
    assert done.returncode == 0, done.stderr
    assert "exiting" in done.stdout
    assert time.monotonic() - started < 40


def test_a_daemon_thread_reports_on_the_gui_thread_and_can_be_interrupted():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QThread, Signal
    from PySide6.QtWidgets import QApplication

    from je_auto_control.gui._daemon_thread import DaemonThread

    app = QApplication.instance() or QApplication([])

    class Counter(DaemonThread):
        tick = Signal(int)

        def run(self):
            count = 0
            while not self.isInterruptionRequested() and count < 500:
                count += 1
                time.sleep(0.005)
            self.tick.emit(count)

    worker = Counter()
    seen, finished = [], []
    worker.tick.connect(lambda n: seen.append((n, QThread.currentThread() is app.thread())))
    worker.finished.connect(lambda: finished.append(threading.current_thread().name))
    worker.start()
    assert worker.isRunning()
    worker.requestInterruption()
    assert worker.wait(5000) and not worker.isRunning()
    deadline = time.monotonic() + 5
    while not (seen and finished) and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert seen and seen[0][0] < 500, "run() did not see the interruption"
    assert seen[0][1] is True, "the signal was not delivered on the GUI thread"
