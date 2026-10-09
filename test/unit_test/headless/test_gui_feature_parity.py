"""Nothing was lost in the GUI rewrite: every feature is reachable, and the numbers can be measured.

The window opens on the three workflow tabs; every registered tab can be
reached from the navigation panel and the View menu and still puts its
commands in the Actions menu; a feature that cannot run says why; the mixed-DPI
geometry helpers agree with what was measured on a 100% + 125% desktop;
``import je_auto_control`` loads no Qt; and both GUI benchmarks produce the
report they document. Offscreen Qt throughout, with fake screens for the
geometry: nothing is shown and no pointer or key is touched.
"""
import importlib.util
import json
import os
import pathlib
import subprocess  # nosec B404  # reason: runs this file's own probes with a fixed argv
import sys
import types

import pytest

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRect  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from je_auto_control.gui import _screen_geometry as geo  # noqa: E402
from je_auto_control.gui.tab_registry import TAB_SPECS  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[3]
BENCHMARKS = ROOT / "benchmarks"
DEFAULT_WORKFLOW = ["record", "script_builder", "remote_desktop"]
# Interactive panels that keep their own controls instead of using the Actions menu.
MENU_EXEMPT_TABS = {"script_builder", "remote_desktop"}


def _child(argv, timeout=240, extra_env=None):
    env = dict(os.environ, PYTHONPATH=str(ROOT), QT_QPA_PLATFORM="offscreen")
    env.update(extra_env or {})
    done = subprocess.run([sys.executable, *argv], capture_output=True, text=True,  # nosec B603  # nosemgrep  # reason: fixed argv, no shell
                          timeout=timeout, env=env, cwd=str(ROOT), check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return done.stdout


# --- the facade stays Qt-free ---------------------------------------------------------------------

def test_import_facade_is_qt_free():
    probe = ("import sys, je_auto_control; "
             "print(sorted(name for name in sys.modules if name.split('.')[0] in ('PySide6', 'shiboken6')))")
    assert _child(["-c", probe]).strip() == "[]"


# --- the real window: default workflow, full catalogue, small window ------------------------------

_PROBE = r"""
import json, os, sys, threading, time
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication, QScrollArea, QTabWidget
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.gui.main_window import AutoControlGUIUI

app = QApplication([])
window = AutoControlGUIUI()
window.show()
app.processEvents()
workspace, navigation = window.auto_control_gui_widget, window.navigation
entries = {entry.key: entry for entry in workspace._tab_entries}
report = {
    "registered": list(entries),
    "default_keys": [row["key"] for row in workspace.list_registered_tabs() if row["visible"]],
    "front": workspace.current_tab_key(),
    "navigation_lists": navigation.visible_keys(),
    "view_menu_lists": [action.data() for action in window._tab_actions],
    "shortcuts_enabled": [window._search_action.isEnabled(), window._sidebar_action.isEnabled()],
}

unreachable, no_actions, menu_mismatch = [], [], []
for key in report["navigation_lists"]:
    navigation.feature_activated.emit(key)
    app.processEvents()
    entry = entries[key]
    if workspace.current_tab_key() != key or workspace.tabs.indexOf(entry.widget) == -1:
        unreachable.append(key)
        continue
    offered = workspace.current_tab_menu_actions()
    shown = [action for action in window._actions_menu.actions() if action.isEnabled()]
    if key not in ("script_builder", "remote_desktop") and not offered:
        no_actions.append(key)
    if len(shown) != len(offered):
        menu_mismatch.append([key, len(shown), len(offered)])
report.update(unreachable=unreachable, no_actions=no_actions, menu_mismatch=menu_mismatch,
              all_open=[row["key"] for row in workspace.list_registered_tabs() if row["visible"]])

# Language and text size change under a full workspace: the list must still be whole and still open tabs.
window.set_text_size(20)
language_wrapper.reset_language("Traditional_Chinese")
app.processEvents()
report["after_language"] = navigation.visible_keys()
report["translated_title"] = workspace.tabs.tabText(workspace.tabs.indexOf(entries["record"].widget))
workspace.hide_tab("variables")
navigation.search.setText("variables")
navigation.activate_first_match()
report["opened_after_language"] = workspace.current_tab_key()
navigation.search.setText("")
language_wrapper.reset_language("English")
window.set_text_size(0)

# A small window: the page keeps its minimum size and its tab scrolls.
window.resize(640, 420)
workspace.activate_tab("auto_click")
for _ in range(3):
    app.processEvents()
page = entries["auto_click"].widget
area = QTabWidget.widget(workspace.tabs, workspace.tabs.indexOf(page)).findChild(QScrollArea)
need = page.minimumSizeHint()
report["small"] = {
    "window": [window.width(), window.height()],
    "page_keeps_minimum": page.width() >= need.width() and page.height() >= need.height(),
    "taller_than_view": need.height() > area.viewport().height(),
    "scrolls": area.verticalScrollBar().maximum() > 0,
}
sys.stdout.write(json.dumps(report))
sys.stdout.flush()
# Tabs opened in a shown window start their first refresh on a worker thread (the USB tabs
# enumerate through a child process). Leaving while one runs was an access violation in
# ExitProcess on Windows, two runs in three, so let them finish first.
deadline = time.monotonic() + 60
while time.monotonic() < deadline and any(t.name.startswith("gui-worker") for t in threading.enumerate()):
    app.processEvents()
    time.sleep(0.02)
os._exit(0)
"""


@pytest.fixture(scope="module")
def window():
    return json.loads(_child(["-c", _PROBE]))


def test_default_workflow_and_full_catalog(window):
    default_keys = window["default_keys"]
    assert default_keys == ['record', 'script_builder', 'remote_desktop']
    assert default_keys == DEFAULT_WORKFLOW
    assert window["front"] == "record"
    registered = [spec.key for spec in TAB_SPECS]
    assert window["registered"] == registered
    assert sorted(window["navigation_lists"]) == sorted(registered)
    assert sorted(window["view_menu_lists"]) == sorted(registered)


def test_every_registered_tab_opens_from_the_navigation_panel(window):
    assert window["unreachable"] == []
    assert sorted(window["all_open"]) == sorted(window["registered"])


def test_every_tab_still_puts_its_commands_in_the_actions_menu(window):
    assert window["no_actions"] == []
    assert window["menu_mismatch"] == []


def test_search_and_panel_shortcuts_are_live(window):
    # Ctrl+B was the dock's own toggle action, which Qt disables for a dock that cannot be closed.
    assert window["shortcuts_enabled"] == [True, True]


def test_navigation_survives_a_language_and_text_size_change(window):
    assert window["after_language"] == window["navigation_lists"]
    assert window["translated_title"] != "Record / Playback"
    assert window["opened_after_language"] == "variables"


def test_small_window_is_usable(window):
    small = window["small"]
    assert small["window"] == [640, 420]
    horizontal_content_clipped = not small["page_keeps_minimum"]
    assert horizontal_content_clipped is False
    assert small["taller_than_view"]
    assert small["scrolls"]


# --- a feature that cannot run says why -----------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_unsupported_feature_has_reason(qapp, monkeypatch):
    from je_auto_control.gui.main_widget import AutoControlGUIWidget

    # ``None`` in sys.modules makes the import fail the way a missing extra does.
    monkeypatch.setitem(sys.modules, "je_auto_control.gui.remote_desktop_tab", None)
    placeholder = AutoControlGUIWidget._build_remote_desktop_tab()  # noqa: SLF001
    text = " ".join(label.text() for label in placeholder.findChildren(QLabel))
    unsupported_feature_has_reason = ("pip install je_auto_control[webrtc]" in text
                                      and "Underlying error: ModuleNotFoundError" in text)
    assert unsupported_feature_has_reason is True
    placeholder.deleteLater()


# --- mixed-DPI geometry, with fake screens --------------------------------------------------------

class _Screen:
    def __init__(self, x, y, width, height, ratio):
        self._geometry, self._ratio = QRect(x, y, width, height), ratio

    def geometry(self):
        return self._geometry

    def devicePixelRatio(self):  # noqa: N802
        return self._ratio


# Measured on Windows in a per-monitor-aware process: the 125% screen at (1920, -164) is
# 1536x864 to Qt and 1920x1080 natively; both keep their top-left corner.
PRIMARY = _Screen(0, 0, 1920, 1080, 1.0)
SCALED = _Screen(1920, -164, 1536, 864, 1.25)


@pytest.fixture
def desktop(monkeypatch):
    monkeypatch.setattr(geo, "sys", types.SimpleNamespace(platform="win32"))
    monkeypatch.setattr(geo, "QGuiApplication", types.SimpleNamespace(screens=lambda: [PRIMARY, SCALED]))


def test_mixed_dpi_geometry(desktop):
    assert geo.capture_ratio(PRIMARY) == 1.0
    assert geo.capture_ratio(SCALED) == 1.25
    # Scaled within the screen, anchored at its corner.
    assert geo.native_region(PRIMARY, QRect(100, 50, 200, 100)) == (100, 50, 200, 100)
    assert geo.native_region(SCALED, QRect(0, 0, 1536, 864)) == (1920, -164, 1920, 1080)
    assert geo.native_region(SCALED, QRect(100, 40, 200, 100)) == (2045, -114, 250, 125)


def test_a_native_point_finds_the_screen_it_is_on(desktop):
    assert geo.screen_at_native(0, 0) is PRIMARY
    assert geo.screen_at_native(1919, 1079) is PRIMARY
    assert geo.screen_at_native(1920, -164) is SCALED
    # Inside the scaled screen's native rectangle, outside its logical one.
    assert geo.screen_at_native(1920 + 1900, -164 + 1000) is SCALED
    assert geo.screen_at_native(1920 + 1920, 0) is None
    assert geo.screen_at_native(1920, -165) is None
    assert geo.screen_at_native(500, 1080) is None


def test_native_and_logical_points_round_trip(desktop):
    assert geo.logical_point(PRIMARY, 640, 480) == QPointF(640, 480)
    assert geo.logical_point(SCALED, 1920 + 1250, -164 + 625) == QPointF(1920 + 1000, -164 + 500)
    for x, y in ((0, 0), (300, 200), (1535, 863)):
        left, top, _width, _height = geo.native_region(SCALED, QRect(x, y, 1, 1))
        back = geo.logical_point(SCALED, left, top)
        assert abs(back.x() - (1920 + x)) <= 0.5
        assert abs(back.y() - (-164 + y)) <= 0.5


def test_macos_takes_points_whatever_the_ratio(monkeypatch):
    monkeypatch.setattr(geo, "sys", types.SimpleNamespace(platform="darwin"))
    retina = _Screen(0, 0, 1512, 982, 2.0)
    monkeypatch.setattr(geo, "QGuiApplication", types.SimpleNamespace(screens=lambda: [retina]))
    assert geo.capture_ratio(retina) == 1.0
    assert geo.native_region(retina, QRect(10, 20, 300, 200)) == (10, 20, 300, 200)
    assert geo.screen_at_native(1511, 981) is retina
    assert geo.screen_at_native(1512, 0) is None
    assert geo.logical_point(retina, 700, 400) == QPointF(700, 400)


# --- the benchmarks -------------------------------------------------------------------------------

def _load(name):
    spec = importlib.util.spec_from_file_location(name, BENCHMARKS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_percentiles_and_summaries():
    bench = _load("_gui_bench")
    samples = list(range(1, 101))
    assert bench.percentile(samples, 95) == 95
    assert bench.percentile(samples, 50) == 50
    assert bench.percentile([7.0], 95) == 7.0
    assert bench.percentile([], 95) == 0.0
    assert bench.summary([3, 1, 2]) == {"median": 2, "min": 1, "max": 3, "samples": [3, 1, 2]}
    assert bench.summary([])["median"] is None


def test_compare_needs_the_same_workload_and_environment():
    bench = _load("_gui_bench")
    env = {"platform": "W", "machine": "x", "python": "3", "pyside6": "6", "qt_platform": "offscreen",
           "screens": [[800, 800, 1.0]]}
    before = {"benchmark": "gui_startup", "workload": "w", "environment": env,
              "startup_ms": {"median": 2000.0, "samples": [2000.0]}, "memory": {"rss_mb": {"median": 100.0}}}
    after = {"benchmark": "gui_startup", "workload": "w", "environment": dict(env, cpu_count=8),
             "startup_ms": {"median": 1500.0, "samples": [1500.0]}, "memory": {"rss_mb": {"median": 110.0}}}
    result = bench.compare(before, after)
    assert result["comparable"] is True
    assert result["changes"]["startup_ms.median"] == {"before": 2000.0, "after": 1500.0, "delta": -500.0,
                                                      "percent": -25.0}
    assert result["changes"]["memory.rss_mb.median"]["delta"] == 10.0
    other = bench.compare(before, dict(after, environment=dict(env, qt_platform="windows"), workload="x"))
    assert other == {"comparable": False, "differs_in": ["workload", "environment.qt_platform"], "changes": {}}


def test_the_startup_benchmark_reports_what_it_documents(tmp_path):
    report_path = tmp_path / "startup.json"
    _child([str(BENCHMARKS / "gui_startup.py"), "--runs", "1", "--output", str(report_path)])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["benchmark"] == "gui_startup"
    assert report["runs"] == 1
    assert report["environment"]["qt_platform"] == "offscreen"
    assert report["environment"]["python"]
    assert report["startup_ms"]["median"] > 0
    assert report["process_ms"]["median"] >= report["startup_ms"]["median"]
    assert set(report["phases_ms"]) == {"import_qt", "import_gui", "build_window", "first_frame"}
    assert report["memory"]["rss_mb"]["median"] > 0
    assert report["tabs_registered"] == len(TAB_SPECS)
    assert report["tabs_built"] < 10
    compared = json.loads(_child([str(BENCHMARKS / "gui_startup.py"), "--compare",
                                  str(report_path), str(report_path)], timeout=60))
    assert compared["comparable"] is True
    assert compared["changes"]["startup_ms.median"]["delta"] == 0


def test_the_workload_benchmark_reports_what_it_documents(tmp_path):
    report_path = tmp_path / "workloads.json"
    _child([str(BENCHMARKS / "gui_workloads.py"), "--tabs", "record,variables,no_such_tab",
            "--output", str(report_path)])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["benchmark"] == "gui_workloads"
    assert report["tabs_opened"] == 2
    assert set(report["first_open_ms"]) == {"record", "variables"}
    assert all(value >= 0 for value in report["first_open_ms"].values())
    assert report["event_loop_p95_ms"] >= 0
    assert report["event_loop_ticks"] > 0
    assert report["idle_event_loop_p95_ms"] >= 0
    assert report["memory"]["rss_mb"] > 0
    assert report["environment"]["qt_platform"] == "offscreen"
    assert len(report["switch_ms"]["samples"]) == 2
    assert len(report["theme_switch_ms"]["samples"]) == 2
