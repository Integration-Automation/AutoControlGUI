"""Auto-click intervals, framework errors in slots, record failures, non-ASCII crops, HUD self-logging, tab menu leaks.

A "0" interval clicked on every event-loop pass; ``AutoControl*`` errors and
decode errors escaped Actions-menu slots and left their status stale; a
failed recording read "Recording..."; ``cv2.imwrite`` failed for non-ASCII
folders; the live HUD's pane filled with its own sampling; every tab-menu
rebuild leaked its submenus and actions. Slots are driven on stub ``self``
objects with the headless call made to fail, as test_r3_gui_slot_exceptions does.
"""
import logging
import os
import sys
import types

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from headless._qt_settle import settle  # noqa: E402
from je_auto_control.utils.exception.exceptions import (  # noqa: E402
    AutoControlActionException, AutoControlAssertionException, AutoControlException,
    AutoControlMouseException,
)


def _raiser(error):
    def raise_it(*_args, **_kwargs):
        raise error
    return raise_it


class _Text:
    def __init__(self, text=""):
        self.value = text

    def text(self):
        return self.value

    def setText(self, value):  # noqa: N802  # reason: mirrors the Qt name
        self.value = value


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_a_zero_interval_is_refused(monkeypatch):
    from je_auto_control.gui import _auto_click_tab as tab
    warned, started = [], []
    monkeypatch.setattr(tab.QMessageBox, "warning", lambda *args: warned.append(args[-1]))
    stub = types.SimpleNamespace(interval_input=_Text("0"),
                                 timer=types.SimpleNamespace(start=lambda: started.append(1)))
    tab.AutoClickTabMixin._start_auto_click(stub)
    assert warned
    assert not started


def test_a_data_source_error_is_shown_by_the_slot(monkeypatch):
    from je_auto_control.gui import data_source_tab as module
    monkeypatch.setattr(module, "load_rows", _raiser(AutoControlActionException("bad query")))
    stub = types.SimpleNamespace(_limit=types.SimpleNamespace(value=lambda: 0),
                                 _build_source=lambda: {}, _status=_Text())
    module.DataSourceTab._on_load(stub)
    assert stub._status.value, "the slot did not report the error"


def test_an_assertion_backend_error_is_shown_once_the_run_is_delivered(monkeypatch):
    # The assertion runs off the GUI thread now, so this needs the real tab.
    from je_auto_control.gui import assertions_tab as module
    _app()
    monkeypatch.setattr(module.ac, "assert_pixel", _raiser(AutoControlException("GetPixel failed")))
    tab = module.AssertionsTab()
    tab._kind.setCurrentIndex(2)  # pixel
    tab._xy.setText("1, 2")
    tab._rgb.setText("0, 0, 0")
    tab._on_run()
    assert settle(tab._runs, "task")
    assert "GetPixel failed" in tab._result.text()


def test_a_self_heal_click_error_is_shown_once_the_run_is_delivered(monkeypatch):
    from je_auto_control.gui import self_healing_tab as module
    _app()
    monkeypatch.setattr(module, "self_heal_click", _raiser(AutoControlMouseException("click failed")))
    tab = module.SelfHealingTab()
    tab._template_input.setText("t.png")
    tab._run(do_click=True)
    assert settle(tab._runs, "task")
    assert "click failed" in tab._status.text()


def test_the_planner_run_slot_shows_an_assertion_failure(monkeypatch):
    from je_auto_control.gui import llm_planner_tab as tab
    _app()
    warned = []
    monkeypatch.setattr(tab.QMessageBox, "warning", lambda *args: warned.append(args[-1]))
    monkeypatch.setattr(tab, "execute_action", _raiser(AutoControlAssertionException("var mismatch")))
    planner = tab.LLMPlannerTab()
    planner._planned_actions = [["AC_assert_var", {}]]
    planner._on_run()
    assert settle(planner._runs, "task")
    assert warned
    assert "var mismatch" in planner._status.text()


def test_a_broken_recording_folder_is_reported(monkeypatch, tmp_path):
    from je_auto_control.gui import trace_replay_tab as tab
    warned = []
    monkeypatch.setattr(tab.QMessageBox, "warning", lambda *args: warned.append(args[-1]))
    monkeypatch.setattr(tab.QFileDialog, "getExistingDirectory", lambda *_args: str(tmp_path))
    stub = types.SimpleNamespace(load_recording=_raiser(ValueError("Expecting value: line 1")))
    tab.TraceReplayTab._on_open(stub)
    assert warned


def test_seeding_variables_is_all_or_nothing(monkeypatch):
    from je_auto_control.utils.script_vars.scope import VariableScope
    scope = VariableScope()
    with pytest.raises(ValueError):
        scope.update_many({"a": 1, "": 2})
    assert "a" not in scope
    from je_auto_control.gui import variables_tab as tab
    stub = types.SimpleNamespace(_seed_text=types.SimpleNamespace(toPlainText=lambda: '{"b": 1, "": 2}'),
                                 _status=_Text(), _refresh=lambda: None)
    tab.VariablesTab._on_seed_json(stub)
    assert stub._status.value


def test_no_input_device_is_a_runtime_error(monkeypatch):
    from je_auto_control.utils.media_assert.media import measure_audio_rms

    class PortAudioError(Exception):
        pass

    fake = types.SimpleNamespace(PortAudioError=PortAudioError, rec=_raiser(PortAudioError("no device")),
                                 wait=lambda: None)
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    with pytest.raises(RuntimeError, match="audio capture failed"):
        measure_audio_rms(0.1)


def test_a_recording_that_does_not_start_is_reported(monkeypatch):
    from je_auto_control.gui import _record_tab as tab
    warned = []
    monkeypatch.setattr(tab.QMessageBox, "warning", lambda *args: warned.append(args[-1]))
    monkeypatch.setattr(tab, "record", lambda: False)
    stub = types.SimpleNamespace(_record_status_key="record_idle", _apply_record_status_label=lambda: None)
    tab.RecordTabMixin._start_record(stub)
    assert warned
    assert stub._record_status_key == "record_idle"


def test_a_template_is_cropped_into_a_non_ascii_folder(monkeypatch, tmp_path):
    from je_auto_control.gui.selector import template_cropper
    monkeypatch.setattr(template_cropper, "open_region_selector", lambda _parent=None: (0, 0, 4, 4))
    monkeypatch.setattr(template_cropper, "_capture_region", lambda _region: np.zeros((4, 4, 3), np.uint8))
    folder = tmp_path / "測試"
    folder.mkdir()
    target = folder / "b.png"
    monkeypatch.setattr(template_cropper, "_validate_output_path", lambda path: str(path))
    assert template_cropper.crop_template_to_file(str(target)) == (0, 0, 4, 4)
    assert target.is_file()


def test_the_hud_does_not_log_its_own_sampling():
    _app()
    from je_auto_control.gui.live_hud_tab import LiveHUDTab
    from je_auto_control.utils.logging.logging_instance import autocontrol_logger
    hud = LiveHUDTab()
    try:
        def sample_mouse():
            autocontrol_logger.info("get_mouse_position")
            return 1, 2

        def sample_pixel(_x, _y):
            autocontrol_logger.info("get_pixel 1 2")
            return (0, 0, 0)

        hud._mouse = types.SimpleNamespace(sample=sample_mouse)
        hud._pixel = types.SimpleNamespace(sample=sample_pixel)
        hud._log_tail.attach(autocontrol_logger)
        previous = autocontrol_logger.level
        autocontrol_logger.setLevel(logging.INFO)
        try:
            hud._tick()
            autocontrol_logger.info("a real event")
        finally:
            autocontrol_logger.setLevel(previous)
            hud._log_tail.detach(autocontrol_logger)
        lines = hud._log_tail.snapshot()
        assert any("a real event" in line for line in lines)
        assert not any("get_mouse_position" in line or "get_pixel" in line for line in lines)
    finally:
        hud.deleteLater()


def test_rebuilding_the_tabs_menu_does_not_leak():
    app = _app()
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QMenu, QWidget

    from je_auto_control.gui.main_window import AutoControlGUIUI
    owner = QWidget()
    view = QMenu(owner)
    entries = [{"title": f"Tab {i}", "visible": True, "key": f"t{i}", "category": "core"} for i in range(5)]
    stub = types.SimpleNamespace(_view_menu=view, _tab_actions=[],
                                 auto_control_gui_widget=types.SimpleNamespace(list_registered_tabs=lambda: entries),
                                 _on_tab_action_toggled=lambda _checked: None)
    stub._add_category_submenu = types.MethodType(AutoControlGUIUI._add_category_submenu, stub)
    counts = []
    for _ in range(3):
        AutoControlGUIUI._rebuild_tabs_menu(stub)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        counts.append(len(view.findChildren(QMenu)))
    assert counts[0] == counts[-1]
    owner.deleteLater()
