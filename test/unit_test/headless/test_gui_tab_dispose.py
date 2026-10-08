"""``dispose()`` frees what a tab holds beyond its widgets, on the call (offscreen Qt, fakes only).

``close_tab(key, release=True)`` called an optional ``dispose()`` that no tab
implemented, so a released tab's timers kept firing and its listeners stayed
registered until Qt got round to deleting the widget. Each test counts what the
tab holds before and after ``dispose()``, without running the event loop.
"""
import ast
import importlib
import logging
import os
import pathlib
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget  # noqa: E402

from je_auto_control.gui import (  # noqa: E402
    _dispose, admin_console_tab, config_sync_tab, email_triggers_tab, hotkeys_tab,
    inspector_tab, live_hud_tab, presence_tab, profiler_tab, rest_api_tab, run_history_tab,
    scheduler_tab, triggers_tab, usb_devices_tab, usb_passthrough_panel, webhooks_tab,
)
from je_auto_control.gui.tab_registry import TAB_SPECS, TabEntry  # noqa: E402
from je_auto_control.gui.task_controller import task_controller  # noqa: E402
from je_auto_control.utils.logging.logging_instance import autocontrol_logger  # noqa: E402
from headless._qt_settle import pump_until  # noqa: E402

_GUI_DIR = pathlib.Path(_dispose.__file__).resolve().parent


@pytest.fixture(autouse=True)
def qapp(monkeypatch):
    app = QApplication.instance() or QApplication([])
    for box in ("warning", "information", "question", "critical"):
        monkeypatch.setattr(QMessageBox, box, lambda *args: None)
    yield app


def _active_timers(widget):
    return sum(1 for timer in widget.findChildren(QTimer) if timer.isActive())


class _Engine:
    """A running scheduler / engine / daemon / watcher / server the tab only polls."""

    is_running, bound_address = True, ("127.0.0.1", 1)

    def _rows(self):
        return []

    list_jobs = list_triggers = list_bindings = list_webhooks = _rows

    def status(self):
        return {"running": False}


_POLLING_TABS = [
    (scheduler_tab, "SchedulerTab", "default_scheduler"),
    (triggers_tab, "TriggersTab", "default_trigger_engine"),
    (hotkeys_tab, "HotkeysTab", "default_hotkey_daemon"),
    (email_triggers_tab, "EmailTriggersTab", "default_email_trigger_watcher"),
    (webhooks_tab, "WebhooksTab", "default_webhook_server"),
    (rest_api_tab, "RestApiTab", "rest_api_registry"),
]


@pytest.mark.parametrize("module, cls, backend", _POLLING_TABS, ids=[case[1] for case in _POLLING_TABS])
def test_a_tab_that_polls_a_backend_stops_polling_and_leaves_the_backend_running(monkeypatch, module, cls, backend):
    engine = _Engine()
    monkeypatch.setattr(module, backend, engine)
    tab = getattr(module, cls)()
    sync = getattr(tab, "sync_with_engine", None)
    if callable(sync):
        sync()                              # what showing the tab does: poll a running engine
    assert _active_timers(tab) == 1
    tab.dispose()
    assert _active_timers(tab) == 0 and engine.is_running
    tab.dispose()                           # safe to call twice


@pytest.mark.parametrize("module, cls", [
    (inspector_tab, "InspectorTab"), (profiler_tab, "ProfilerTab"), (run_history_tab, "RunHistoryTab"),
])
def test_a_tab_with_a_refresh_timer_stops_it(module, cls, monkeypatch, tmp_path):
    if module is run_history_tab:
        from je_auto_control.utils.run_history.history_store import HistoryStore
        monkeypatch.setattr(run_history_tab, "default_history_store", HistoryStore(tmp_path / "history.db"))
    tab = getattr(module, cls)()
    assert _active_timers(tab) == 1
    tab.dispose()
    assert _active_timers(tab) == 0


def test_the_admin_console_stops_its_thumbnail_timer(monkeypatch, tmp_path):
    from je_auto_control.utils.admin.admin_client import AdminConsoleClient
    monkeypatch.setattr(admin_console_tab, "default_admin_console",
                        lambda: AdminConsoleClient(persist_path=tmp_path / "hosts.json"))
    tab = admin_console_tab.AdminConsoleTab()
    assert _active_timers(tab) == 1
    tab.dispose()
    assert _active_timers(tab) == 0


def test_the_presence_tab_leaves_the_registry_and_stops_its_timer(monkeypatch):
    from je_auto_control.utils.remote_desktop.presence import PresenceRegistry
    registry = PresenceRegistry()
    monkeypatch.setattr(presence_tab, "default_presence_registry", lambda: registry)
    tab = presence_tab.PresenceTab()
    assert len(registry._listeners) == 1 and _active_timers(tab) == 1  # noqa: SLF001
    tab.dispose()
    assert registry._listeners == [] and _active_timers(tab) == 0  # noqa: SLF001
    tab.dispose()


def test_the_live_hud_takes_its_tail_off_the_logger_and_stops_sampling(monkeypatch):
    monkeypatch.setattr(live_hud_tab.LiveHUDTab, "isVisible", lambda self: True)
    before = len(autocontrol_logger.handlers)
    hud = live_hud_tab.LiveHUDTab()
    hud._start()
    assert len(autocontrol_logger.handlers) == before + 1 and _active_timers(hud) == 1
    hud.dispose()
    assert len(autocontrol_logger.handlers) == before and _active_timers(hud) == 0
    assert all(isinstance(handler, logging.Handler) for handler in autocontrol_logger.handlers)


@pytest.fixture()
def watcher(monkeypatch):
    holds = []
    for module in (usb_devices_tab, usb_passthrough_panel):
        monkeypatch.setattr(module, "hold_default_watcher", lambda: holds.append(1))
        monkeypatch.setattr(module, "release_default_watcher", lambda background=False: holds.pop())
    return holds


def test_the_usb_devices_tab_gives_back_its_share_of_the_watcher(watcher):
    tab = usb_devices_tab.UsbDevicesTab()
    tab._auto_check.setChecked(True)
    assert len(watcher) == 1 and _active_timers(tab) == 1
    tab.dispose()
    assert watcher == [] and _active_timers(tab) == 0
    tab.dispose()
    assert watcher == []                    # given back once


def test_the_usb_sharing_panel_closes_its_loopback_and_gives_back_the_watcher(watcher, monkeypatch, tmp_path):
    from je_auto_control.utils.usb.passthrough import UsbAcl
    closed, switched = threading.Event(), []
    monkeypatch.setattr(usb_passthrough_panel, "enable_usb_passthrough", switched.append)

    class _Loop:
        def close(self):
            closed.set()

    panel = usb_passthrough_panel.UsbPassthroughPanel(acl=UsbAcl(path=tmp_path / "acl.json"),
                                                      loopback_factory=_Loop)
    panel._enable_sharing()
    panel._auto_check.setChecked(True)
    assert len(watcher) == 1 and _active_timers(panel) == 1 and panel._loopback is not None
    panel.dispose()
    assert watcher == [] and _active_timers(panel) == 0 and panel._loopback is None
    assert closed.wait(10.0)                # off the GUI thread, as for the Stop command
    assert pump_until(lambda: switched == [True, False])
    panel.dispose()


def test_a_usb_sharing_panel_that_never_shared_leaves_the_passthrough_flag_alone(watcher, monkeypatch, tmp_path):
    from je_auto_control.utils.usb.passthrough import UsbAcl
    switched = []
    monkeypatch.setattr(usb_passthrough_panel, "enable_usb_passthrough", switched.append)
    panel = usb_passthrough_panel.UsbPassthroughPanel(acl=UsbAcl(path=tmp_path / "acl.json"))
    panel.dispose()
    assert switched == []


def test_config_sync_cancels_the_sync_that_is_out(monkeypatch):
    monkeypatch.setattr(config_sync_tab.session, "config_sync_status", lambda _url, _user: {})
    tab = config_sync_tab.ConfigSyncTab()
    cancel = threading.Event()
    tab._cancel_slot[:] = [cancel]
    tab.dispose()
    assert cancel.is_set()


def test_dispose_cancels_the_tabs_background_tasks(qapp):
    owner = QWidget()
    release, released = threading.Event(), []

    def work(token):
        token.on_cancel(lambda: released.append(True))
        release.wait(30.0)

    controller = task_controller()
    before = controller.active_count()
    controller.submit(work, owner=owner)
    _dispose.release_resources(owner)
    assert released == [True]
    release.set()
    assert pump_until(lambda: controller.active_count() == before)


def test_a_release_that_raises_does_not_keep_the_others_from_running():
    owner, ran = QWidget(), []
    timer = QTimer(owner)
    timer.start(60_000)

    def broken():
        raise RuntimeError("already gone")

    _dispose.release_resources(owner, broken, lambda: ran.append(1))
    assert ran == [1] and not timer.isActive()


def test_releasing_a_tab_through_the_registry_runs_its_dispose(monkeypatch):
    monkeypatch.setattr(scheduler_tab, "default_scheduler", _Engine())
    spec = next(spec for spec in TAB_SPECS if spec.class_name == "SchedulerTab")
    entry = TabEntry(key=spec.key, title_key=spec.title_key, category=spec.category,
                     factory=scheduler_tab.SchedulerTab)
    tab = entry.widget
    tab.sync_with_engine()
    assert _active_timers(tab) == 1
    assert entry.release() and _active_timers(tab) == 0 and not entry.built


# --- every tab that holds something has the hook -----------------------------------------------------------------

#: A tab class whose source does one of these at any point holds something deletion alone releases late.
_HOLDS = ("QTimer(", ".add_listener(", "hold_default_watcher(", ".attach(")


def _tab_classes():
    for spec in TAB_SPECS:
        if spec.module and spec.class_name and spec.module.startswith("je_auto_control.gui."):
            yield spec.module, spec.class_name


def _class_source(module_name, class_name):
    module = importlib.import_module(module_name)
    path = pathlib.Path(module.__file__)
    if path.name == "__init__.py":          # a package that re-exports its tab class
        path = pathlib.Path(importlib.import_module(getattr(module, class_name).__module__).__file__)
    source = path.read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return ast.get_source_segment(source, node) or ""
    return ""


def test_every_registered_tab_that_holds_a_timer_or_a_listener_implements_dispose():
    missing = []
    for module_name, class_name in _tab_classes():
        try:
            source = _class_source(module_name, class_name)
        except ImportError:                 # an optional extra is not installed here
            continue
        if any(marker in source for marker in _HOLDS) and "def dispose(self)" not in source:
            missing.append(f"{module_name}.{class_name}")
    assert missing == [], f"tabs that start a timer or register a listener without dispose(): {missing}"


def test_the_guard_reads_real_tab_classes():
    checked = [name for _module, name in _tab_classes()]
    assert "SchedulerTab" in checked and "PresenceTab" in checked and len(checked) >= 30
    assert _GUI_DIR.joinpath("_dispose.py").is_file()
