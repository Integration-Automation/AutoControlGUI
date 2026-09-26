"""Engine tabs show the engine's own state; the VLM tab calls the model off the GUI thread.

The Hotkeys, Scheduler and Triggers tabs kept their own running flag, so an
engine started from Tools > Start still read "stopped" and was not polled;
the VLM tab's locate and click froze the window for the model round trip.
"""
import os
import threading
import time
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


def _pump(app, predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    return predicate()


def test_the_engines_report_whether_they_run():
    from je_auto_control.utils.scheduler.scheduler import Scheduler
    scheduler = Scheduler(executor=lambda *_args: None)
    assert scheduler.is_running is False
    scheduler.start()
    try:
        assert scheduler.is_running is True
    finally:
        scheduler.stop()
    assert scheduler.is_running is False


@pytest.mark.parametrize("module_name, cls_name, engine_name, running_key", [
    ("scheduler_tab", "SchedulerTab", "default_scheduler", "sch_status_running"),
    ("triggers_tab", "TriggersTab", "default_trigger_engine", "tr_engine_running"),
    ("hotkeys_tab", "HotkeysTab", "default_hotkey_daemon", "hk_daemon_running"),
])
def test_a_tab_shows_an_engine_started_elsewhere(qapp, monkeypatch, module_name, cls_name, engine_name,
                                                 running_key):
    from je_auto_control.gui import hotkeys_tab, scheduler_tab, triggers_tab
    module = {"hotkeys_tab": hotkeys_tab, "scheduler_tab": scheduler_tab, "triggers_tab": triggers_tab}[module_name]
    real = getattr(module, engine_name)
    fake = types.SimpleNamespace(is_running=False)
    for name in dir(real):
        if not name.startswith("_") and name != "is_running":
            setattr(fake, name, lambda *args, **kwargs: [])
    monkeypatch.setattr(module, engine_name, fake)
    tab = getattr(module, cls_name)()
    try:
        fake.is_running = True                     # Tools > Start, or a script
        tab.sync_with_engine()
        assert tab._timer.isActive()
        assert tab._status.text() == module.language_wrapper.translate(running_key, running_key)
        fake.is_running = False
        tab.sync_with_engine()
        assert not tab._timer.isActive()
    finally:
        tab.deleteLater()


def test_tools_start_resyncs_every_engine_tab():
    from je_auto_control.gui.main_widget import AutoControlGUIWidget
    synced = []
    entries = [types.SimpleNamespace(widget=types.SimpleNamespace(sync_with_engine=lambda: synced.append(1))),
               types.SimpleNamespace(widget=types.SimpleNamespace())]
    AutoControlGUIWidget.sync_engine_tabs(types.SimpleNamespace(_tab_entries=entries))
    assert synced == [1]


def test_the_vlm_tab_calls_the_model_off_the_gui_thread(qapp, monkeypatch):
    from je_auto_control.gui import vlm_tab
    threads = []
    monkeypatch.setattr(vlm_tab, "locate_by_description",
                        lambda description, model=None: threads.append(threading.get_ident()) or (10, 20))
    tab = vlm_tab.VLMTab()
    try:
        tab._description.setText("the OK button")
        tab._on_locate()
        assert _pump(qapp, lambda: "10" in tab._last_result.text())
        assert threads and threads[0] != threading.get_ident()
    finally:
        tab.deleteLater()
