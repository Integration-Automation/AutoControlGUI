"""GUI tabs at the edges the audit found (offscreen Qt; nothing is clicked or captured).

Slots let framework errors escape instead of showing them; USB sharing and
the Live HUD were released only in ``closeEvent``, which a tab never gets;
hidden tabs had no parent and outlived their window; a worker's unexpected
exception never reached ``on_fail``; the Script Builder rewrote a choice it
did not list; the main window's language listener and each USB prompt's
dialog outlived their owners.
"""
import json
import os
import subprocess  # nosec B404  # reason: runs this test's own probe script
import sys
import textwrap
import threading
import time
import types
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QObject, Signal  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QComboBox, QDialog, QLineEdit, QTabWidget, QTableWidget, QTableWidgetItem,
    QTextEdit, QWidget,
)

from je_auto_control.utils.exception.exceptions import (  # noqa: E402
    AutoControlActionException, AutoControlScreenException, ImageNotFoundException,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _flush_deletes(app) -> None:
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


class _Boxes:
    """Stands in for QMessageBox: records instead of blocking."""

    def __init__(self):
        self.shown = []

    def warning(self, *args):
        self.shown.append(args)

    information = critical = warning


# --- slots show framework errors -----------------------------------------------------------

def test_the_recording_editor_shows_a_malformed_file(qapp, tmp_path, monkeypatch):
    from je_auto_control.gui import recording_editor_tab
    boxes = _Boxes()
    monkeypatch.setattr(recording_editor_tab, "QMessageBox", boxes)
    tab = recording_editor_tab.RecordingEditorTab()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    tab._path_input.setText(str(bad))  # noqa: SLF001
    tab._load()  # noqa: SLF001
    tab._path_input.setText(str(tmp_path / "missing.json"))  # noqa: SLF001
    tab._load()  # noqa: SLF001
    assert len(boxes.shown) == 2
    tab.deleteLater()


def test_open_script_shows_a_malformed_file(qapp, tmp_path):
    from je_auto_control.gui.main_widget import AutoControlGUIWidget
    bad = tmp_path / "bad.json"
    bad.write_text("[[", encoding="utf-8")
    fake = types.SimpleNamespace(
        _find_entry=lambda key: None, script_path_input=QLineEdit(),
        script_editor=QTextEdit(), script_result_text=QTextEdit())
    AutoControlGUIWidget.open_script_file(fake, str(bad))
    assert fake.script_result_text.toPlainText().startswith("Error loading")


def test_image_detection_shows_no_match(qapp, monkeypatch):
    from je_auto_control.gui import _image_detect_tab as tab

    def not_found(*args, **kwargs):
        raise ImageNotFoundException("not on screen")

    for name in ("locate_image_center", "locate_all_image", "locate_and_click"):
        monkeypatch.setattr(tab, name, not_found)
    fake = types.SimpleNamespace(_get_detect_params=lambda: ("t.png", 0.8, False),
                                 detect_result_text=QTextEdit(), mouse_button_combo=QComboBox())
    for slot in ("_locate_image", "_locate_all", "_locate_click"):
        fake.detect_result_text.clear()
        getattr(tab.ImageDetectTabMixin, slot)(fake)
        assert "not on screen" in fake.detect_result_text.toPlainText()


def test_screenshot_shows_a_bad_region(qapp, monkeypatch):
    from je_auto_control.gui import _screenshot_tab as tab

    def bad_region(**kwargs):
        raise AutoControlScreenException("bad region")

    monkeypatch.setattr(tab, "screenshot", bad_region)
    fake = types.SimpleNamespace(ss_path_input=QLineEdit(), ss_region_input=QLineEdit("100,100,50,50"),
                                 ss_result_text=QTextEdit())
    tab.ScreenshotTabMixin._take_screenshot(fake)
    assert "bad region" in fake.ss_result_text.toPlainText()


def test_the_manual_script_shows_an_unknown_command(qapp):
    from je_auto_control.gui._script_tab import ScriptTabMixin
    fake = types.SimpleNamespace(script_editor=QTextEdit('[["AC_no_such_command"]]'),
                                 script_result_text=QTextEdit())
    ScriptTabMixin._execute_manual_script(fake)
    text = fake.script_result_text.toPlainText()
    assert text.startswith("Error") or "AC_no_such_command" in text
    fake.script_editor.setPlainText("[]")
    ScriptTabMixin._execute_manual_script(fake)
    assert fake.script_result_text.toPlainText().startswith("Error")


def test_focusing_a_window_that_has_closed_is_shown(qapp, monkeypatch):
    from je_auto_control.gui import window_tab

    def gone(*args, **kwargs):
        raise AutoControlActionException("focus_window: no window matches")

    boxes = _Boxes()
    monkeypatch.setattr(window_tab, "QMessageBox", boxes)
    monkeypatch.setattr(window_tab, "focus_window", gone)
    monkeypatch.setattr(window_tab, "close_window_by_title", gone)
    fake = types.SimpleNamespace(_selected_title=lambda: "Gone", refresh=lambda: None)
    window_tab.WindowManagerTab._on_focus(fake)
    window_tab.WindowManagerTab._on_close(fake)
    assert len(boxes.shown) == 2


# --- USB sharing -----------------------------------------------------------------------------

@pytest.fixture()
def usb_panel(qapp, tmp_path):
    panel_mod = pytest.importorskip("je_auto_control.gui.usb_passthrough_panel",
                                    reason="gui stack not importable", exc_type=ImportError)
    from je_auto_control.utils.usb.passthrough import UsbAcl, UsbLoopback
    from je_auto_control.utils.usb.passthrough.backend import BackendDevice, FakeUsbBackend
    acl = UsbAcl(path=tmp_path / "acl.json")
    backend = FakeUsbBackend(devices=[BackendDevice(vendor_id="1050", product_id="0407", serial="S")])
    closed = []

    class _Loopback(UsbLoopback):
        def close(self):
            closed.append(1)
            super().close()

    panel = panel_mod.UsbPassthroughPanel(
        acl=acl, loopback_factory=lambda: _Loopback(backend=backend, acl=acl, viewer_id="t"))
    return panel, closed


def test_destroying_the_usb_panel_stops_sharing(qapp, usb_panel):
    from je_auto_control.utils.usb.passthrough.flags import is_usb_passthrough_enabled
    panel, closed = usb_panel
    panel._enable_sharing()  # noqa: SLF001
    assert is_usb_passthrough_enabled()
    panel.deleteLater()
    del panel
    _flush_deletes(qapp)
    assert closed == [1] and not is_usb_passthrough_enabled()


def test_a_usb_row_without_ids_is_reported_not_raised(qapp, usb_panel):
    panel, _closed = usb_panel
    table: QTableWidget = panel._local_table  # noqa: SLF001
    table.setRowCount(1)
    for col in range(table.columnCount()):
        table.setItem(0, col, QTableWidgetItem("-"))
    table.selectRow(0)
    panel._set_policy(True)  # noqa: SLF001
    assert "USB id" in panel._viewer_status.text()  # noqa: SLF001
    panel.deleteLater()


# --- Live HUD -----------------------------------------------------------------------------------

def test_the_live_hud_polls_only_while_shown_and_detaches_its_tail(qapp):
    from je_auto_control.gui.live_hud_tab import LiveHUDTab
    hud = LiveHUDTab()
    tail = hud._log_tail  # noqa: SLF001
    hud._start()  # noqa: SLF001
    assert tail in autocontrol_logger.handlers and not hud._timer.isActive()  # noqa: SLF001
    hud.show()
    assert hud._timer.isActive()  # noqa: SLF001
    hud.hide()
    assert not hud._timer.isActive()  # noqa: SLF001
    hud.deleteLater()
    del hud
    _flush_deletes(qapp)
    assert tail not in autocontrol_logger.handlers


# --- hidden tabs, workers, enum values, prompt dialogs ----------------------------------------------

def test_a_hidden_tab_is_owned_and_stays_hidden(qapp):
    from je_auto_control.gui.main_widget import AutoControlGUIWidget

    class _Owner(QWidget):
        def __init__(self):
            super().__init__()
            self._tab_entries = []
            self.tabs = QTabWidget(self)

    owner, page = _Owner(), QWidget()
    AutoControlGUIWidget._add_tab(owner, "k", "k", page)
    owner.show()
    assert page.parent() is owner and not page.isVisible()
    owner.deleteLater()


class _Crashing(QObject):
    finished = Signal(object)

    def run(self):
        raise AttributeError("'list' object has no attribute 'get'")


def test_a_worker_crash_reaches_on_fail(qapp):
    from je_auto_control.gui._worker_thread import start_worker
    owner, failures, ended = QWidget(), [], []
    start_worker(owner, _Crashing(), on_done=lambda value: None,
                 on_thread_done=lambda: ended.append(1), on_fail=failures.append)
    deadline = time.monotonic() + 5
    while not ended and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert failures == ["AttributeError: 'list' object has no attribute 'get'"]
    owner.deleteLater()


def test_a_choice_outside_the_list_is_kept(qapp):
    from je_auto_control.gui.script_builder import step_form_view as sfv
    combo = QComboBox()
    combo.addItems(["mouse_left", "mouse_right"])
    sfv._set_enum_value(combo, "mouse_x1")  # noqa: SLF001
    assert combo.currentText() == "mouse_x1"
    sfv._set_enum_value(combo, "mouse_right")  # noqa: SLF001
    assert combo.currentText() == "mouse_right" and combo.count() == 3


def test_each_usb_prompt_dialog_is_deleted(qapp, monkeypatch):
    prompt = pytest.importorskip("je_auto_control.gui.usb_passthrough_prompt",
                                 reason="gui stack not importable", exc_type=ImportError)
    monkeypatch.setattr(prompt.UsbPassthroughPromptDialog, "exec",
                        lambda self: QDialog.DialogCode.Rejected)
    parent = QWidget()
    bridge = prompt.PromptBridge(dialog_parent=parent)
    for _ in range(3):
        bridge._show_dialog("1050", "0407", "", "", {}, threading.Event())  # noqa: SLF001
    _flush_deletes(qapp)
    assert parent.findChildren(prompt.UsbPassthroughPromptDialog) == []
    parent.deleteLater()


# --- the real window: listeners go with it --------------------------------------------------------

_WINDOW_PROBE = textwrap.dedent("""
    import gc, json, os
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication
    from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
    from je_auto_control.utils.remote_desktop.presence import default_presence_registry
    app = QApplication([])
    before = (len(language_wrapper._listeners), len(default_presence_registry()._listeners))
    from je_auto_control.gui.main_window import AutoControlGUIUI
    window = AutoControlGUIUI()
    during = (len(language_wrapper._listeners), len(default_presence_registry()._listeners))
    window.deleteLater()
    del window
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    gc.collect()
    after = (len(language_wrapper._listeners), len(default_presence_registry()._listeners))
    print(json.dumps({"before": before, "during": during, "after": after}))
""")


def test_destroying_the_window_removes_its_listeners():
    env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT), QT_QPA_PLATFORM="offscreen")
    argv = [sys.executable, "-c", _WINDOW_PROBE]
    done = subprocess.run(argv, capture_output=True, text=True, timeout=180, env=env, cwd=str(_REPO_ROOT), check=False)  # nosec B603  # nosemgrep  # reason: this test's own probe, fixed argv
    assert done.returncode == 0, done.stderr[-2000:]
    counts = json.loads(done.stdout.strip().splitlines()[-1])
    # [language listeners, presence listeners]: each window adds one of each.
    assert all(d > b for d, b in zip(counts["during"], counts["before"])), counts
    assert counts["after"] == counts["before"], counts
