"""Tab commands that wait on a browser, a device, a model or a peer no longer hold the GUI thread.

Offscreen Qt against fakes: each backend call is replaced by one that waits on
a gate, so the test can see the slot return first and the outcome arrive later.
"""
import os
import threading
import time
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox  # noqa: E402

from headless._qt_settle import settle  # noqa: E402
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper  # noqa: E402

_WAIT = 10.0


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class _Gate:
    """A backend call that blocks until released and remembers where it ran."""

    def __init__(self, result=None, error=None) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls: list = []
        self.threads: list = []
        self.result = result
        self.error = error

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        self.threads.append(threading.get_ident())
        self.entered.set()
        self.release.wait(_WAIT)
        if self.error is not None:
            raise self.error
        return self.result

    def off_gui_thread(self) -> bool:
        return bool(self.threads) and all(ident != threading.get_ident() for ident in self.threads)


@pytest.fixture
def boxes(monkeypatch):
    _app = QApplication.instance() or QApplication([])
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: shown.append(args[-1]))
    monkeypatch.setattr(QMessageBox, "information", lambda *args: shown.append(args[-1]))
    return shown


def _returns_at_once(slot) -> None:
    started = time.monotonic()
    slot()
    assert time.monotonic() - started < 5.0, "the slot held the GUI thread"


# --- WebRunner ----------------------------------------------------------------------------------------------

def test_webrunner_calls_run_off_thread_one_at_a_time(boxes, monkeypatch):
    from je_auto_control.gui import webrunner_tab as module
    gate = _Gate(result={"opened": True})
    monkeypatch.setattr(module, "web_open", gate)
    monkeypatch.setattr(module, "web_quit", lambda: "bye")
    tab = module.WebRunnerTab()
    tab._url_input.setText("https://example.invalid")
    _returns_at_once(tab._on_open)
    assert gate.entered.wait(_WAIT)
    tab._on_quit()                      # refused while the open is running
    assert _t("task_busy") in tab._output.toPlainText()
    gate.release.set()
    assert settle(tab._runs, "task")
    assert gate.off_gui_thread()
    assert gate.calls == [(("https://example.invalid",), {"browser": "chrome"})]
    assert f"{_t('web_open_btn')}: " in tab._output.toPlainText()
    tab._on_quit()
    assert settle(tab._runs, "task")
    assert f"{_t('web_quit_btn')}: bye" in tab._output.toPlainText()


def test_webrunner_bridge_error_is_shown(boxes, monkeypatch):
    from je_auto_control.gui import webrunner_tab as module
    monkeypatch.setattr(module, "run_webrunner_action",
                        lambda _action: (_ for _ in ()).throw(module.WebRunnerBridgeError("no driver")))
    tab = module.WebRunnerTab()
    tab._action_input.setText("WR_to_url")
    tab._params_input.setPlainText('{"url": "x"}')
    tab._on_run_freeform()
    assert settle(tab._runs, "task")
    assert "no driver" in tab._output.toPlainText()


# --- media checks -------------------------------------------------------------------------------------------

def test_media_checks_run_off_thread(boxes, monkeypatch):
    from je_auto_control.gui import media_checks_tab as module
    audio = _Gate(result=types.SimpleNamespace(message="heard sound"))
    video = _Gate(error=OSError("no such video"))
    monkeypatch.setattr(module.ac, "assert_audio_activity", audio)
    monkeypatch.setattr(module.ac, "assert_video_changes", video)
    tab = module.MediaChecksTab()
    _returns_at_once(tab._on_audio)
    assert tab._result.text() == _t("task_running")
    assert audio.entered.wait(_WAIT)
    tab._on_video()                     # one check at a time
    assert not video.calls
    audio.release.set()
    assert settle(tab._runs, "task")
    assert tab._result.text() == "heard sound"
    assert audio.off_gui_thread()
    assert audio.calls[0][1]["raise_on_fail"] is False

    tab._video_path.setText("clip.mp4")
    video.release.set()
    tab._on_video()
    assert settle(tab._runs, "task")
    assert tab._result.text() == "no such video"
    assert video.calls[0][0] == ("clip.mp4",)


# --- assertions / self healing ------------------------------------------------------------------------------

def test_assertion_runs_off_thread(boxes, monkeypatch):
    from je_auto_control.gui import assertions_tab as module
    result = types.SimpleNamespace(to_dict=lambda: {"passed": True, "message": "found"})
    gate = _Gate(result=result)
    monkeypatch.setattr(module.ac, "assert_by_description", gate)
    tab = module.AssertionsTab()
    tab._kind.setCurrentIndex(4)        # vlm
    tab._target.setText("the OK button")
    _returns_at_once(tab._on_run)
    assert tab._result.text() == _t("task_running")
    assert gate.entered.wait(_WAIT)
    gate.release.set()
    assert settle(tab._runs, "task")
    assert gate.off_gui_thread()
    assert tab._result.text().startswith(_t("assert_passed"))
    assert "found" in tab._result.text()


def test_a_short_pixel_coordinate_is_still_explained(boxes):
    from je_auto_control.gui import assertions_tab as module
    tab = module.AssertionsTab()
    tab._kind.setCurrentIndex(2)        # pixel
    tab._xy.setText("5")
    tab._on_run()
    assert settle(tab._runs, "task")
    assert "x,y" in tab._result.text()


def test_self_heal_locate_runs_off_thread(boxes, monkeypatch):
    from je_auto_control.gui import self_healing_tab as module
    outcome = module.HealOutcome(found=True, method="template", coordinates=(3, 4))
    gate = _Gate(result=outcome)
    monkeypatch.setattr(module, "self_heal_locate", gate)
    tab = module.SelfHealingTab()
    tab._template_input.setText("button.png")
    _returns_at_once(tab._on_locate)
    assert tab._status.text() == _t("task_running")
    assert gate.entered.wait(_WAIT)
    gate.release.set()
    assert settle(tab._runs, "task")
    assert gate.off_gui_thread()
    assert "(template)" in tab._status.text()
    assert gate.calls[0][1]["template_path"] == "button.png"


# --- Quick Connect: files dropped on the remote screen ----------------------------------------------------------

class _FakeSession:
    connected = True

    def __init__(self, send) -> None:
        self.send_file = send


@pytest.fixture
def quick_connect(boxes, monkeypatch, tmp_path):
    from je_auto_control.gui.remote_desktop import connection_screen
    from je_auto_control.utils.remote_desktop.address_book import AddressBook
    book = AddressBook(tmp_path / "book.json")           # never the operator's own address book
    monkeypatch.setattr(connection_screen, "default_address_book", lambda: book)
    screen = connection_screen.QuickConnectScreen()
    yield screen
    screen._refresh_timer.stop()


def test_dropped_files_upload_off_thread(quick_connect, boxes, monkeypatch):
    screen = quick_connect
    gate = _Gate()
    viewer = _FakeSession(gate)
    monkeypatch.setattr(screen, "_own_viewer", lambda: viewer)
    _returns_at_once(lambda: screen._on_files_dropped(["C:/tmp/a.txt", "C:/tmp/b.txt"]))
    assert screen._uploads.running
    assert gate.entered.wait(_WAIT)
    screen._on_files_dropped(["C:/tmp/c.txt"])
    assert boxes == [_t("rd_file_busy")]
    gate.release.set()
    assert settle(screen._uploads, "task")
    assert gate.off_gui_thread()
    assert [call[0] for call in gate.calls] == [("C:/tmp/a.txt", "~/a.txt"), ("C:/tmp/b.txt", "~/b.txt")]


def test_a_failed_upload_is_reported_and_a_disconnect_is_not(quick_connect, boxes, monkeypatch):
    screen = quick_connect
    failing = _Gate(error=OSError("disk full on the host"))
    failing.release.set()
    monkeypatch.setattr(screen, "_own_viewer", lambda: _FakeSession(failing))
    screen._on_files_dropped(["a.txt", "b.txt"])
    assert settle(screen._uploads, "task")
    assert boxes == ["disk full on the host"]
    assert len(failing.calls) == 1

    boxes.clear()
    closing = _Gate(error=OSError("socket closed"))
    monkeypatch.setattr(screen, "_own_viewer", lambda: _FakeSession(closing))
    screen._on_files_dropped(["a.txt"])
    assert closing.entered.wait(_WAIT)
    monkeypatch.setattr(screen, "_own_viewer", lambda: None)
    screen._disconnect()                # cancels the upload: its failure is not news
    closing.release.set()
    assert settle(screen._uploads, "task")
    deadline = time.monotonic() + 0.3
    while time.monotonic() < deadline:
        QApplication.instance().processEvents()
        time.sleep(0.01)
    assert boxes == []


def test_nothing_is_uploaded_without_a_session(quick_connect, monkeypatch):
    monkeypatch.setattr(quick_connect, "_own_viewer", lambda: None)
    quick_connect._on_files_dropped(["a.txt"])
    assert not quick_connect._uploads.running


# --- WebRTC panels ------------------------------------------------------------------------------------------

@pytest.fixture
def webrtc_panel(boxes):
    pytest.importorskip("av")
    pytest.importorskip("aiortc")
    from je_auto_control.gui.remote_desktop import webrtc_panel as module
    return module


def test_apply_answer_runs_off_thread_and_consumes_the_session(webrtc_panel, boxes):
    panel = webrtc_panel._WebRTCHostPanel()
    gate = _Gate()
    host = types.SimpleNamespace(accept_session_answer=gate)
    panel._multi_host, panel._manual_session_id = host, "sess-1"
    panel._answer_input.setPlainText("v=0 answer")
    _returns_at_once(panel._on_apply_answer)
    assert panel._status_label.text() == _t("task_running")
    assert gate.entered.wait(_WAIT)
    panel._on_apply_answer()            # one at a time
    assert len(gate.calls) == 1
    gate.release.set()
    assert settle(panel, "_answer_task")
    assert gate.off_gui_thread()
    assert gate.calls[0][0] == ("sess-1", "v=0 answer")
    assert panel._manual_session_id is None
    assert panel._status_label.text() == _t("rd_webrtc_answer_applied")


def test_a_refused_answer_keeps_the_session_for_another_try(webrtc_panel, boxes):
    panel = webrtc_panel._WebRTCHostPanel()
    gate = _Gate(error=ValueError("bad SDP"))
    gate.release.set()
    panel._multi_host = types.SimpleNamespace(accept_session_answer=gate)
    panel._manual_session_id = "sess-2"
    panel._answer_input.setPlainText("garbage")
    panel._on_apply_answer()
    assert settle(panel, "_answer_task")
    assert panel._manual_session_id == "sess-2"
    assert any("bad SDP" in str(box) for box in boxes) or "bad SDP" in panel._status_label.text()


def test_an_answer_for_a_host_stopped_meanwhile_changes_nothing(webrtc_panel, boxes):
    panel = webrtc_panel._WebRTCHostPanel()
    gate = _Gate()
    panel._multi_host = types.SimpleNamespace(accept_session_answer=gate)
    panel._manual_session_id = "sess-3"
    panel._answer_input.setPlainText("v=0")
    panel._on_apply_answer()
    assert gate.entered.wait(_WAIT)
    panel._multi_host = None            # stopped while the answer was being applied
    gate.release.set()
    assert settle(panel, "_answer_task")
    assert panel._status_label.text() != _t("rd_webrtc_answer_applied")


def test_host_file_push_runs_off_thread(webrtc_panel, boxes, monkeypatch):
    panel = webrtc_panel._WebRTCHostPanel()
    gate = _Gate(result=2)
    panel._multi_host = types.SimpleNamespace(session_count=lambda: 2, broadcast_file=gate)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: ("C:/tmp/report.pdf", ""))
    _returns_at_once(panel._on_push_file)
    assert "report.pdf" in panel._status_label.text()
    assert gate.entered.wait(_WAIT)
    panel._on_push_file()
    assert boxes == [_t("rd_file_busy")]
    gate.release.set()
    assert settle(panel, "_file_task")
    assert gate.off_gui_thread()
    assert gate.calls[0][0] == ("C:/tmp/report.pdf",)
    assert boxes[-1] == _t("rd_webrtc_push_done").format(n=2, name="C:/tmp/report.pdf")


def test_viewer_send_and_upload_run_off_thread(webrtc_panel, boxes, monkeypatch):
    panel = webrtc_panel._WebRTCViewerPanel()
    gate = _Gate()
    panel._viewer = types.SimpleNamespace(authenticated=True, send_file=gate,
                                          request_inbox_listing=lambda: None)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: ("C:/tmp/one.bin", ""))
    _returns_at_once(panel._on_send_file)
    assert "one.bin" in panel._status_label.text()
    assert gate.entered.wait(_WAIT)
    panel._on_upload_paths(["C:/tmp/two.bin"])
    assert boxes == [_t("rd_file_busy")]
    gate.release.set()
    assert settle(panel, "_file_task")
    assert gate.off_gui_thread()
    assert panel._status_label.text() == _t("rd_webrtc_file_sent").format(name="C:/tmp/one.bin")

    panel._on_upload_paths(["C:/tmp/two.bin", "C:/tmp/three.bin"])
    assert settle(panel, "_file_task")
    assert [call[0] for call in gate.calls] == [("C:/tmp/one.bin",), ("C:/tmp/two.bin",), ("C:/tmp/three.bin",)]
    assert panel._status_label.text() == _t("rd_webrtc_upload_done").format(n=2)
    panel._viewer = None                # nothing left for the delayed inbox refresh to ask


def test_an_upload_that_fails_for_every_file_is_reported(webrtc_panel, boxes):
    panel = webrtc_panel._WebRTCViewerPanel()
    failing = _Gate(error=RuntimeError("files channel not open yet"))
    failing.release.set()
    panel._viewer = types.SimpleNamespace(authenticated=True, send_file=failing)
    panel._on_upload_paths(["a.bin", "b.bin"])
    assert settle(panel, "_file_task")
    assert boxes == ["files channel not open yet"]
    assert len(failing.calls) == 2
    panel._viewer = None
