"""The window shell: remembered state, pages that scroll, drawn close crosses, releasing a tab.

Offscreen Qt throughout; nothing is shown and nothing is clicked on the
desktop. The settings tests write only under ``tmp_path``: the suite itself
runs with the store switched off (``test/conftest.py``), which the first tests
here hold it to.
"""
import json
import os
import pathlib
import subprocess  # nosec B404  # reason: runs this file's own probe with a fixed argv
import sys

import pytest

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractButton, QApplication, QLabel, QScrollArea, QTabWidget, QWidget,
)

from je_auto_control.gui.tab_registry import TAB_SPECS, TabEntry  # noqa: E402
from je_auto_control.gui.window_settings import (  # noqa: E402
    DEFAULT_NAVIGATION_WIDTH, SETTINGS_ENV, WindowSettings, WindowState, settings_path,
)
from je_auto_control.gui._tab_close_icon import cache_directory, close_button_rules, cross_file  # noqa: E402
from je_auto_control.gui.theme import DARK, LIGHT  # noqa: E402
from je_auto_control.gui.workspace_tabs import PageHolder, WorkspaceTabWidget  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _settle(app) -> None:
    for _ in range(3):
        app.processEvents()


# --- where the state is kept ------------------------------------------------------------------------

def test_the_suite_runs_with_the_store_switched_off():
    assert os.environ.get(SETTINGS_ENV) == "off"
    store = WindowSettings()
    assert settings_path() is None
    assert store.path is None
    assert store.save(WindowState(theme="light")) is False
    assert store.load() == WindowState()


@pytest.mark.parametrize("value", ["", "off", "OFF", "0", "none", " false "])
def test_the_variable_switches_the_store_off(monkeypatch, value):
    monkeypatch.setenv(SETTINGS_ENV, value)
    assert settings_path() is None


def test_the_default_file_follows_the_home_directory(monkeypatch, tmp_path):
    monkeypatch.delenv(SETTINGS_ENV)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert settings_path() == tmp_path / ".je_auto_control" / "gui_settings.ini"


def test_the_variable_names_another_file(monkeypatch, tmp_path):
    monkeypatch.setenv(SETTINGS_ENV, str(tmp_path / "look.ini"))
    assert settings_path() == pathlib.Path(os.path.realpath(tmp_path / "look.ini"))


def test_state_round_trips_through_the_file(qapp, tmp_path):
    path = tmp_path / "deep" / "gui.ini"
    saved = WindowState(theme="light", text_size=14, navigation_visible=False,
                        navigation_width=333, geometry=b"\x01\x02\x00\xff")
    assert WindowSettings(path).save(saved) is True
    assert path.is_file()
    assert WindowSettings(path).load() == saved


def test_a_missing_file_is_a_first_run(qapp, tmp_path):
    assert WindowSettings(tmp_path / "absent.ini").load() == WindowState()
    assert not (tmp_path / "absent.ini").exists()


def test_values_out_of_range_fall_back_to_the_defaults(qapp, tmp_path):
    path = tmp_path / "gui.ini"
    path.write_text("[main_window]\ntheme=neon\ntext_size=999\nnavigation_visible=perhaps\n"
                    "navigation_width=5\ngeometry=not-bytes\n", encoding="utf-8")
    state = WindowSettings(path).load()
    assert (state.theme, state.text_size, state.navigation_visible, state.navigation_width) == (
        "dark", 0, True, DEFAULT_NAVIGATION_WIDTH)


def test_an_unwritable_place_is_reported_not_raised(qapp, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    assert WindowSettings(blocker / "below" / "gui.ini").save(WindowState()) is False


# --- pages scroll; callers still speak in pages -------------------------------------------------------

class _Big(QWidget):
    """A form that needs more room than a narrow window has."""

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(600, 500)

    sizeHint = minimumSizeHint  # noqa: N815


def test_the_page_relation_survives_the_wrapper(qapp):
    tabs = WorkspaceTabWidget()
    first, second = QLabel("one"), QLabel("two")
    assert tabs.addTab(first, "One") == 0
    assert tabs.insertTab(0, second, "Two") == 0
    assert (tabs.indexOf(first), tabs.indexOf(second), tabs.indexOf(QLabel())) == (1, 0, -1)
    assert tabs.widget(0) is second
    assert tabs.widget(1) is first
    assert tabs.widget(7) is None
    tabs.setCurrentWidget(first)
    assert tabs.currentIndex() == 1
    assert tabs.currentWidget() is first
    # What Qt itself holds is the holder, with the page inside a scroll area.
    holder = QTabWidget.widget(tabs, 1)
    assert isinstance(holder, PageHolder)
    assert holder.findChild(QScrollArea) is not None
    assert holder.isAncestorOf(first)
    tabs.deleteLater()


def test_a_removed_page_is_kept_hidden_and_can_come_back(qapp):
    tabs = WorkspaceTabWidget()
    page = QLabel("kept")
    tabs.addTab(page, "Kept")
    tabs.removeTab(0)
    assert tabs.count() == 0
    assert tabs.indexOf(page) == -1
    assert page.parent() is tabs
    assert page.isHidden()
    tabs.addTab(page, "Kept")
    assert tabs.indexOf(page) == 0
    assert tabs.currentWidget() is page
    tabs.clear()
    assert tabs.count() == 0
    assert page.parent() is tabs
    tabs.deleteLater()


def test_a_narrow_window_scrolls_the_page_instead_of_squeezing_it(qapp):
    tabs = WorkspaceTabWidget()
    page = _Big()
    tabs.addTab(page, "Big")
    tabs.resize(320, 260)
    tabs.show()
    _settle(qapp)
    area = QTabWidget.widget(tabs, 0).findChild(QScrollArea)
    assert page.width() >= 600
    assert page.height() >= 500
    assert area.viewport().width() < 600
    assert area.horizontalScrollBar().maximum() > 0
    assert area.verticalScrollBar().maximum() > 0
    tabs.resize(900, 800)
    _settle(qapp)
    assert area.horizontalScrollBar().maximum() == 0
    assert page.width() > 600
    tabs.hide()
    tabs.deleteLater()


def test_a_panel_that_scrolls_itself_is_not_wrapped_again(qapp):
    tabs = WorkspaceTabWidget()
    panel = _Big()
    tabs.addTab(panel, "Panel", scrollable=False)
    holder = QTabWidget.widget(tabs, 0)
    assert holder.findChild(QScrollArea) is None
    assert panel.parent() is holder
    assert tabs.indexOf(panel) == 0
    assert tabs.currentWidget() is panel
    assert not tabs.is_scrollable(0)
    tabs.resize(320, 260)
    tabs.show()
    _settle(qapp)
    assert panel.width() < 600
    tabs.hide()
    tabs.deleteLater()


def test_a_deferred_tab_has_a_title_and_no_page_until_filled(qapp):
    tabs = WorkspaceTabWidget()
    tabs.addTab(QLabel("front"), "Front")
    assert tabs.insert_deferred_tab(1, "later", "Later") == 1
    assert tabs.tabText(1) == "Later"
    assert tabs.widget(1) is None
    assert tabs.deferred_key(1) == "later"
    assert tabs.index_of_deferred("later") == 1
    assert tabs.deferred_key(0) == ""
    assert tabs.index_of_deferred("") == -1
    page = QLabel("built")
    assert tabs.fill_deferred("later", page) is True
    assert tabs.widget(1) is page
    assert tabs.indexOf(page) == 1
    assert tabs.deferred_key(1) == ""
    assert tabs.index_of_deferred("later") == -1
    assert tabs.fill_deferred("later", QLabel()) is False
    tabs.deleteLater()


# --- close buttons --------------------------------------------------------------------------------

def test_the_cross_is_drawn_in_code_and_cached(qapp, tmp_path):
    path = cross_file("#E7E9EE", 255, tmp_path)
    assert path == tmp_path / "tab_close_e7e9ee_255.png"
    assert sorted(item.name for item in tmp_path.iterdir()) == [
        "tab_close_e7e9ee_255.png", "tab_close_e7e9ee_255@2x.png", "tab_close_e7e9ee_255@3x.png"]
    for name, side in (("tab_close_e7e9ee_255.png", 16), ("tab_close_e7e9ee_255@3x.png", 48)):
        image = QImage(str(tmp_path / name))
        assert (image.width(), image.height()) == (side, side)
        centre, corner = image.pixelColor(side // 2, side // 2), image.pixelColor(0, 0)
        assert corner.alpha() == 0
        assert centre.alpha() > 200
        assert (centre.red(), centre.green(), centre.blue()) == (0xE7, 0xE9, 0xEE)
    stamp = path.stat().st_mtime_ns
    assert cross_file("#e7e9ee", 255, tmp_path) == path
    assert path.stat().st_mtime_ns == stamp


def test_the_style_sheet_points_the_close_button_at_the_cross(qapp, tmp_path):
    dark, light = close_button_rules(DARK, tmp_path), close_button_rules(LIGHT, tmp_path)
    assert dark != light
    for rules, tokens in ((dark, DARK), (light, LIGHT)):
        assert "QTabBar::close-button {" in rules
        assert "QTabBar::close-button:hover {" in rules
        rest = tmp_path / f"tab_close_{tokens.text_muted.lstrip('#')}_255.png"
        hover = tmp_path / f"tab_close_{tokens.text.lstrip('#')}_255.png"
        assert rest.is_file()
        assert hover.is_file()
        assert f'url("{rest.as_posix()}")' in rules
        assert f'url("{hover.as_posix()}")' in rules
        assert tokens.hover in rules


def test_an_unwritable_cache_leaves_the_styles_own_icon(qapp, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    assert cross_file("#ffffff", 255, blocker / "below") is None
    assert close_button_rules(DARK, blocker / "below") == ""


def test_the_cache_follows_the_home_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert cache_directory() == tmp_path / ".je_auto_control" / "gui_cache"


def test_the_tab_bar_keeps_qts_own_close_buttons(qapp):
    """Buttons of our own in the bar made probes crash on exit; see ``_tab_close_icon``."""
    tabs = WorkspaceTabWidget()
    tabs.setTabsClosable(True)
    for name in ("a", "b"):
        tabs.addTab(QLabel(name), name)
    asked = []
    tabs.tabCloseRequested.connect(asked.append)
    buttons = [child for child in tabs.tabBar().children() if type(child) is QAbstractButton]
    assert len(buttons) == 2
    for button in buttons:
        button.click()
    assert sorted(asked) == [0, 1]
    tabs.deleteLater()


# --- releasing a tab (no Qt needed) ---------------------------------------------------------------

class _Tab:
    def __init__(self, log, fail=False):
        self.log, self.fail = log, fail

    def dispose(self):
        self.log.append("dispose")
        if self.fail:
            raise RuntimeError("timer already gone")

    def deleteLater(self):  # noqa: N802
        self.log.append("deleted")


def test_release_disposes_deletes_and_the_next_open_builds_anew():
    log = []
    entry = TabEntry("k", "tab_k", lambda: _Tab(log))
    assert entry.release() is False
    assert log == []  # never built: nothing to let go of
    first = entry.widget
    assert entry.release() is True
    assert log == ["dispose", "deleted"]
    assert not entry.built
    assert entry.widget is not first
    assert entry.built


def test_release_without_a_dispose_hook_still_deletes():
    log = []

    class _Plain:
        def deleteLater(self):  # noqa: N802
            log.append("deleted")

    entry = TabEntry("k", "tab_k", _Plain)
    _ = entry.widget
    assert entry.release() is True
    assert log == ["deleted"]


def test_a_failing_dispose_still_deletes_the_widget():
    log = []
    entry = TabEntry("k", "tab_k", lambda: _Tab(log, fail=True))
    _ = entry.widget
    with pytest.raises(RuntimeError):
        entry.release()
    assert log == ["dispose", "deleted"]
    assert not entry.built


def test_a_fixed_widget_is_never_released():
    log = []
    fixed = _Tab(log)
    entry = TabEntry("k", "tab_k", lambda: fixed, releasable=False)
    _ = entry.widget
    assert entry.release() is False
    assert log == []
    assert entry.widget is fixed


def test_only_remote_desktop_opts_out_of_page_scrolling():
    assert [spec.key for spec in TAB_SPECS if not spec.scrollable] == ["remote_desktop"]


# --- the real window, twice ------------------------------------------------------------------------

_PROBE = r"""
import json, os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication
from je_auto_control.gui.main_window import AutoControlGUIUI
from je_auto_control.gui.theme import LIGHT, font_rule

app = QApplication([])
window = AutoControlGUIUI()
window.show()
for _ in range(3):
    app.processEvents()
workspace = window.auto_control_gui_widget
report = {
    "theme": window._theme_name, "text": window._user_font_pt,
    "sheet": LIGHT.window in window.styleSheet() and font_rule(14) in window.styleSheet(),
    "nav_hidden": window._navigation_dock.isHidden(), "nav_width": window._navigation_dock.width(),
    "size": [window.width(), window.height()],
    "close_rule": "QTabBar::close-button" in window.styleSheet(),
    "checked_theme": [a.data() for a in window.findChildren(type(window._search_action))
                      if a.isCheckable() and a.isChecked() and a.data() in ("dark", "light")],
}
if sys.argv[1] == "first":
    window.set_theme("light")
    window.set_text_size(14)
    window.resize(700, 500)
    window.resizeDocks([window._navigation_dock], [330], Qt.Orientation.Horizontal)
    for _ in range(3):
        app.processEvents()
    report["width_set"] = window._navigation_dock.width()
    window.close()
elif sys.argv[1] == "second":
    report["toggle_enabled"] = window._sidebar_action.isEnabled() and window._sidebar_action.isChecked()
    window._sidebar_action.trigger()          # Ctrl+B: saved at once, not only on close
    report["hidden_now"] = window._navigation_dock.isHidden()
else:
    kept = workspace.open_tab("variables")
    report["open_returns_widget"] = kept is workspace._find_entry("variables").widget
    report["closed_kept"] = [workspace.close_tab("variables"), workspace._find_entry("variables").widget is kept]
    seen = []
    kept.dispose = lambda: seen.append("dispose")
    report["released"] = workspace.close_tab("variables", release=True)
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    report["disposed"] = seen
    report["built_after_release"] = workspace._find_entry("variables").built
    fresh = workspace.open_tab("variables")
    report["fresh_widget"] = fresh is not kept and workspace.current_tab_key() == "variables"
    report["own_form"] = [workspace.close_tab("record", release=True), workspace._find_entry("record").built]
    report["unknown"] = [workspace.open_tab("nope"), workspace.close_tab("nope", release=True)]
sys.stdout.write(json.dumps(report))
sys.stdout.flush()
os._exit(0)
"""


def _run(mode: str, settings: str) -> dict:
    env = dict(os.environ, PYTHONPATH=str(ROOT), QT_QPA_PLATFORM="offscreen")
    env[SETTINGS_ENV] = settings
    done = subprocess.run([sys.executable, "-c", _PROBE, mode], capture_output=True, text=True,  # nosec B603  # nosemgrep  # reason: fixed argv, no shell
                          timeout=180, env=env, cwd=str(ROOT), check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    path = tmp_path_factory.mktemp("gui-settings") / "gui.ini"
    first = _run("first", str(path))
    second = _run("second", str(path))
    third = _run("third", str(path))
    return first, second, third, path


def test_a_first_run_has_the_defaults(runs):
    first = runs[0]
    assert (first["theme"], first["text"], first["nav_hidden"]) == ("dark", 0, False)
    assert first["size"] == [1280, 800]
    assert first["checked_theme"] == ["dark"]
    assert first["close_rule"]


def test_the_next_run_looks_like_the_last_one(runs):
    first, second, _third, path = runs
    assert path.is_file()
    assert (second["theme"], second["text"], second["sheet"]) == ("light", 14, True)
    assert second["checked_theme"] == ["light"]
    assert second["size"] == [700, 500]      # inside the 800x800 offscreen screen, so not clamped
    assert abs(second["nav_width"] - first["width_set"]) <= 2
    assert first["width_set"] != DEFAULT_NAVIGATION_WIDTH


def test_hiding_the_panel_is_remembered_without_closing(runs):
    _first, second, third, _path = runs
    assert second["toggle_enabled"]
    assert second["nav_hidden"] is False
    assert second["hidden_now"] is True
    assert third["nav_hidden"] is True
    # A hidden panel keeps the width it had.
    assert WindowSettings(runs[3]).load().navigation_width == runs[0]["width_set"]


def test_closing_keeps_the_widget_and_releasing_lets_it_go(runs):
    third = runs[2]
    assert third["open_returns_widget"]
    assert third["closed_kept"] == [False, True]
    assert third["released"] is True
    assert third["disposed"] == ["dispose"]
    assert third["built_after_release"] is False
    assert third["fresh_widget"]
    # The widget's own forms hold attributes its slots read; they are closed, never released.
    assert third["own_form"] == [False, True]
    assert third["unknown"] == [None, False]
