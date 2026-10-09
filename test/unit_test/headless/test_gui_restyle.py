"""A theme or text-size change restyles what shows, once (offscreen Qt; the real window in a child process).

``set_theme`` set the window's style sheet twice -- the theme, then the theme
plus the font rule -- and each time Qt re-applied it to every widget of every
open tab, visible or not: 1.0-2.0 s with all 50 tabs open.
"""
import json
import os
import pathlib
import subprocess  # nosec B404  # reason: runs this file's own probe with a fixed argv
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget  # noqa: E402

from je_auto_control.gui.window_settings import SETTINGS_ENV  # noqa: E402
from je_auto_control.gui.workspace_tabs import WorkspaceTabWidget, real_window  # noqa: E402
from headless._qt_settle import pump_until  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def _page(text):
    page = QWidget()
    layout = QVBoxLayout(page)
    label = QLabel(text)
    layout.addWidget(label)
    page.label = label
    return page


@pytest.fixture
def workspace(qapp):
    window = QWidget()
    layout = QVBoxLayout(window)
    tabs = WorkspaceTabWidget()
    layout.addWidget(tabs)
    pages = [_page(name) for name in ("one", "two", "three")]
    tabs.addTab(pages[0], "one")
    tabs.addTab(pages[1], "two")
    tabs.addTab(pages[2], "three", scrollable=False)
    window.setStyleSheet("* { font-size: 9pt; }")
    yield window, tabs, pages
    tabs.finish_restyle()
    window.deleteLater()


def _size(page):
    page.label.ensurePolished()
    return page.label.font().pointSize()


def _in_window(page, window):
    return page.window() is window


def test_a_restyle_touches_the_selected_page_and_defers_the_others(workspace):
    window, tabs, pages = workspace
    assert [_size(page) for page in pages] == [9, 9, 9]
    parked = tabs.restyle(lambda: window.setStyleSheet("* { font-size: 17pt; }"))
    assert parked == 2
    assert tabs.parked_pages() == 2
    assert _in_window(pages[0], window)
    assert _size(pages[0]) == 17
    assert not _in_window(pages[1], window)
    assert not _in_window(pages[2], window)
    # Still the tab's page for every caller that speaks in pages.
    assert [tabs.indexOf(page) for page in pages] == [0, 1, 2]
    assert [tabs.widget(index) for index in range(3)] == pages
    assert pump_until(lambda: tabs.parked_pages() == 0)
    assert all(_in_window(page, window) for page in pages)
    assert [_size(page) for page in pages] == [17, 17, 17], "a page that came back kept the old style"
    assert pump_until(lambda: tabs._parking is None)       # the parking widget goes once it is empty


def test_selecting_a_tab_puts_its_page_back_at_once(workspace):
    window, tabs, pages = workspace
    tabs.restyle(lambda: window.setStyleSheet("* { font-size: 15pt; }"))
    tabs.setCurrentIndex(2)
    assert _in_window(pages[2], window)
    assert _size(pages[2]) == 15
    assert tabs.parked_pages() == 1
    assert tabs.currentWidget() is pages[2]


def test_a_second_restyle_before_the_first_drained_ends_on_the_last_style(workspace):
    window, tabs, pages = workspace
    tabs.restyle(lambda: window.setStyleSheet("* { font-size: 15pt; }"))
    assert tabs.restyle(lambda: window.setStyleSheet("* { font-size: 21pt; }")) == 0
    tabs.finish_restyle()
    assert tabs.parked_pages() == 0
    assert [_size(page) for page in pages] == [21, 21, 21]


def test_closing_a_tab_whose_page_is_parked_keeps_the_page(workspace):
    window, tabs, pages = workspace
    tabs.restyle(lambda: window.setStyleSheet("* { font-size: 15pt; }"))
    tabs.removeTab(1)
    assert pages[1].parent() is tabs
    assert pages[1].isHidden()
    assert tabs.count() == 2
    assert tabs.indexOf(pages[1]) == -1
    assert tabs.indexOf(pages[2]) == 1
    tabs.finish_restyle()
    tabs.insertTab(1, pages[1], "two")
    assert tabs.widget(1) is pages[1]
    assert _size(pages[1]) == 15


def test_the_page_of_a_closed_tab_is_not_restyled_in_the_same_slot(workspace):
    """A closed tab's page is kept as a hidden child of the tab widget, and was restyled with the window."""
    window, tabs, pages = workspace
    tabs.removeTab(1)
    assert pages[1].parent() is tabs
    assert _size(pages[1]) == 9
    parked = tabs.restyle(lambda: window.setStyleSheet("* { font-size: 17pt; }"))
    assert parked == 2
    assert tabs.parked_pages() == 2  # the other tab's page and the closed one
    assert not _in_window(pages[1], window)
    assert pages[1].isHidden()
    assert pump_until(lambda: tabs.parked_pages() == 0)
    assert pages[1].parent() is tabs
    assert pages[1].isHidden()
    assert tabs.indexOf(pages[1]) == -1
    assert _size(pages[1]) == 17, "the closed page came back with the old style"
    assert pump_until(lambda: tabs._parking is None)


def test_reopening_a_closed_tab_during_a_restyle_takes_its_page_out_of_the_queue(workspace):
    window, tabs, pages = workspace
    tabs.removeTab(1)
    tabs.restyle(lambda: window.setStyleSheet("* { font-size: 15pt; }"))
    tabs.insertTab(1, pages[1], "two")
    tabs.setCurrentIndex(1)
    assert _in_window(pages[1], window)
    assert _size(pages[1]) == 15
    assert not pages[1].isHidden()
    assert pump_until(lambda: tabs.parked_pages() == 0)
    assert pump_until(lambda: tabs._parking is None)
    assert tabs.widget(1) is pages[1]
    assert _in_window(pages[1], window)  # not taken back out as "closed"


def test_finishing_a_restyle_brings_closed_pages_back_too(workspace):
    window, tabs, pages = workspace
    tabs.removeTab(2)
    tabs.restyle(lambda: window.setStyleSheet("* { font-size: 15pt; }"))
    tabs.finish_restyle()
    assert tabs.parked_pages() == 0
    assert pages[2].parent() is tabs
    assert pages[2].isHidden()
    assert _size(pages[2]) == 15


def test_a_parked_page_still_finds_the_real_window(workspace):
    """``page.window()`` is the parking widget for a few event-loop turns; ``real_window`` sees through it."""
    window, tabs, pages = workspace
    tabs.removeTab(2)
    assert real_window(pages[1]) is window
    assert real_window(pages[2]) is window
    tabs.restyle(lambda: window.setStyleSheet("* { font-size: 15pt; }"))
    parking = pages[1].window()
    assert parking is not window
    assert real_window(pages[1]) is window
    assert real_window(pages[1].label) is window
    assert real_window(pages[2]) is window                      # the closed tab's page
    parking.show()                          # what ``self.window().showNormal()`` in a page would have done
    parking.showNormal()
    assert not parking.isVisible()
    tabs.finish_restyle()
    assert real_window(pages[1]) is window


def test_the_webrtc_tray_raises_the_main_window_even_while_its_page_is_parked(workspace, monkeypatch):
    pytest.importorskip("av", exc_type=ImportError)
    pytest.importorskip("aiortc", exc_type=ImportError)
    from je_auto_control.gui.remote_desktop import webrtc_panel
    window, tabs, _pages = workspace
    panel = webrtc_panel._WebRTCHostPanel()
    tabs.addTab(panel, "host")
    raised = []
    for name in ("showNormal", "raise_", "activateWindow"):
        monkeypatch.setattr(window, name, lambda name=name: raised.append(name), raising=False)
    tabs.restyle(lambda: window.setStyleSheet("* { font-size: 15pt; }"))
    assert panel.window() is not window
    panel._on_tray_open()
    assert raised == ["showNormal", "raise_", "activateWindow"]
    assert not panel.window().isVisible()   # the parking widget was not shown as a window
    tabs.finish_restyle()


def test_a_restyle_that_raises_still_brings_the_pages_back(workspace):
    _window, tabs, pages = workspace

    def broken():
        raise RuntimeError("bad style")

    with pytest.raises(RuntimeError):
        tabs.restyle(broken)
    assert pump_until(lambda: tabs.parked_pages() == 0)
    assert tabs.widget(1) is pages[1]


def test_a_single_tab_has_nothing_to_park(qapp):
    tabs = WorkspaceTabWidget()
    tabs.addTab(_page("only"), "only")
    applied = []
    assert tabs.restyle(lambda: applied.append(1)) == 0
    assert applied == [1]
    assert tabs._parking is None or pump_until(lambda: tabs._parking is None)
    tabs.deleteLater()


# --- the real window ---------------------------------------------------------------------------------------------

_PROBE = r"""
import json, os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication, QLabel, QWidget
from je_auto_control.gui.main_window import AutoControlGUIUI
from je_auto_control.gui.theme import DARK, LIGHT, font_rule

app = QApplication([])
window = AutoControlGUIUI()
window.show()
app.processEvents()
workspace = window.auto_control_gui_widget
for key in ("variables", "scheduler", "hotkeys", "triggers"):
    workspace.open_tab(key)
    app.processEvents()
tabs = workspace.tabs
sets = []
original = window.setStyleSheet
window.setStyleSheet = lambda text: (sets.append(text), original(text))[1]
before_pt = window._effective_font_pt(window._user_font_pt)
window.set_theme("light")
report = {
    "sheet_sets_for_a_theme": len(sets),
    "theme_and_font_in_one": LIGHT.window in sets[0] and font_rule(before_pt) in sets[0],
    "parked_right_after": tabs.parked_pages(),
    "pages": sum(1 for index in range(tabs.count()) if tabs.widget(index) is not None),
    "current_in_window": tabs.currentWidget().window() is window,
}
del sets[:]
window.set_text_size(window._user_font_pt)       # the same size again
report["sets_for_an_unchanged_size"] = len(sets)
window.set_text_size(16)
report["sets_for_a_new_size"] = len(sets)
while tabs.parked_pages():
    app.processEvents()
pages = [tabs.widget(index) for index in range(tabs.count())]
report["all_back"] = all(page is None or page.window() is window for page in pages)
labels = [label for page in pages if page is not None for label in page.findChildren(QLabel)]
for label in labels:
    label.ensurePolished()
report["labels"] = len(labels)
report["label_sizes"] = sorted({label.font().pointSize() for label in labels if not label.styleSheet()})
report["label_text_colours"] = sorted({label.palette().windowText().color().name() for label in labels
                                       if not label.styleSheet()})
report["light_text"] = LIGHT.text
sys.stdout.write(json.dumps(report))
sys.stdout.flush()
os._exit(0)
"""


@pytest.fixture(scope="module")
def window_report():
    env = dict(os.environ, PYTHONPATH=str(ROOT), QT_QPA_PLATFORM="offscreen")
    env[SETTINGS_ENV] = "off"
    done = subprocess.run([sys.executable, "-c", _PROBE], capture_output=True, text=True,  # nosec B603  # nosemgrep  # reason: fixed argv, no shell
                          timeout=180, env=env, cwd=str(ROOT), check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


def test_a_theme_switch_sets_the_style_sheet_once_with_the_font_rule(window_report):
    assert window_report["sheet_sets_for_a_theme"] == 1
    assert window_report["theme_and_font_in_one"]


def test_a_theme_switch_leaves_only_the_selected_page_in_the_tree(window_report):
    # Tabs nobody opened yet have no page; of the built ones only the selected one stays.
    assert window_report["pages"] >= 4
    assert window_report["parked_right_after"] == window_report["pages"] - 1
    assert window_report["current_in_window"]


def test_setting_the_same_text_size_again_restyles_nothing(window_report):
    assert window_report["sets_for_an_unchanged_size"] == 0
    assert window_report["sets_for_a_new_size"] == 1


def test_every_page_comes_back_with_the_new_theme_and_size(window_report):
    assert window_report["all_back"]
    assert window_report["labels"] > 10
    assert window_report["label_sizes"] == [16]
    assert window_report["label_text_colours"] == [window_report["light_text"]]
