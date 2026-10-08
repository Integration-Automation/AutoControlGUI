"""Theme tokens, the navigation panel's search, and the window that hosts both."""
import json
import os
import pathlib
import re
import subprocess  # nosec B404  # reason: runs this file's own probe with a fixed argv
import sys

import pytest

from je_auto_control.gui.tab_registry import TAB_SPECS
from je_auto_control.gui.theme import (
    DARK, DEFAULT_THEME, LIGHT, THEMES, build_stylesheet, font_rule, theme_named,
)

CATEGORIES = (("core", "menu_view_cat_core", "Core"), ("system", "menu_view_cat_system", "System"))
ENTRIES = [
    {"key": "record", "title": "Record / Playback", "category": "core", "visible": True},
    {"key": "usb_devices", "title": "USB Devices", "category": "system", "visible": False},
    {"key": "usb_browser", "title": "USB Browser", "category": "system", "visible": False},
    {"key": "live_hud", "title": "Live HUD", "category": "detection", "visible": False},
]


# --- theme: no Qt needed -----------------------------------------------------

@pytest.mark.parametrize("tokens", [DARK, LIGHT], ids=lambda tokens: tokens.name)
def test_the_stylesheet_is_complete(tokens):
    sheet = build_stylesheet(tokens)
    assert not re.search(r"\{[a-z_]+\}", sheet), "an unfilled placeholder is left"
    assert sheet.count("{") == sheet.count("}")
    for colour in (tokens.window, tokens.surface, tokens.text, tokens.accent, tokens.border, tokens.selection):
        assert colour in sheet
    assert "#NavigationPanel" in sheet and "QTabBar::tab:selected" in sheet


def test_the_two_themes_differ_and_an_unknown_name_falls_back():
    assert set(THEMES) == {"dark", "light"}
    assert build_stylesheet(DARK) != build_stylesheet(LIGHT)
    assert theme_named("light") is LIGHT
    assert theme_named("no-such-theme") is THEMES[DEFAULT_THEME]


def test_the_font_rule_sets_only_the_size():
    assert font_rule(14) == "* { font-size: 14pt; }"


def test_text_contrast_is_readable_in_both_themes():
    def luminance(colour):
        channels = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    def contrast(first, second):
        high, low = sorted((luminance(first), luminance(second)), reverse=True)
        return (high + 0.05) / (low + 0.05)

    for tokens in (DARK, LIGHT):
        assert contrast(tokens.text, tokens.window) >= 7, tokens.name
        assert contrast(tokens.text, tokens.surface) >= 7, tokens.name
        assert contrast(tokens.text_muted, tokens.surface) >= 4.5, tokens.name
        assert contrast(tokens.accent_text, tokens.accent) >= 4.5, tokens.name


# --- navigation panel --------------------------------------------------------

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    widgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    return widgets.QApplication.instance() or widgets.QApplication([])


@pytest.fixture
def panel(qapp):
    from je_auto_control.gui.navigation import NavigationPanel
    navigation = NavigationPanel()
    navigation.set_entries(ENTRIES, CATEGORIES)
    yield navigation
    navigation.deleteLater()


def test_every_entry_is_listed_under_its_category(panel):
    assert panel.visible_keys() == ["record", "usb_devices", "usb_browser", "live_hud"]
    groups = [panel.tree.topLevelItem(i).text(0) for i in range(panel.tree.topLevelItemCount())]
    assert groups == ["Core", "System", "Detection"]          # an unlisted category comes last


def test_search_matches_title_key_and_category(panel):
    assert panel.apply_filter("usb") == 2
    assert panel.visible_keys() == ["usb_devices", "usb_browser"]
    assert panel.apply_filter("USB brow") == 1                 # every word, any case
    assert panel.apply_filter("live_hud") == 1                 # the key as written in scripts
    assert panel.apply_filter("system") == 2                   # the category name
    assert panel.apply_filter("") == 4


def test_no_match_shows_the_empty_state_instead_of_a_blank_list(panel):
    assert panel.apply_filter("zzz") == 0
    assert panel.tree.isHidden() and not panel.empty.isHidden()
    panel.apply_filter("")
    assert not panel.tree.isHidden() and panel.empty.isHidden()


def test_return_in_the_search_box_opens_the_first_match(panel):
    chosen = []
    panel.feature_activated.connect(chosen.append)
    panel.search.setText("usb")
    panel.search.returnPressed.emit()
    assert chosen == ["usb_devices"]
    panel.search.setText("zzz")
    panel.search.returnPressed.emit()
    assert chosen == ["usb_devices"]                           # nothing to open


def test_clicking_a_category_heading_opens_nothing(panel):
    chosen = []
    panel.feature_activated.connect(chosen.append)
    panel.tree.itemClicked.emit(panel.tree.topLevelItem(0), 0)
    panel.tree.itemClicked.emit(panel.tree.topLevelItem(0).child(0), 0)
    assert chosen == ["record"]


def test_a_search_survives_the_list_being_refreshed(panel):
    panel.search.setText("usb")
    panel.set_entries(ENTRIES, CATEGORIES)                     # what a tab opening triggers
    assert panel.visible_keys() == ["usb_devices", "usb_browser"]


# --- the window --------------------------------------------------------------
# In a child process: the window builds Remote Desktop and the Script Builder,
# whose native helper threads must not be torn down inside this interpreter.

_PROBE = r"""
import json, os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from je_auto_control.gui.main_window import AutoControlGUIUI
from je_auto_control.gui.tab_registry import TAB_SPECS
from je_auto_control.gui.theme import DARK, LIGHT, font_rule

app = QApplication.instance() or QApplication([])
window = AutoControlGUIUI()
window.show()
app.processEvents()
workspace, navigation = window.auto_control_gui_widget, window.navigation
report = {"reachable": sorted(navigation.visible_keys()), "registered": sorted(s.key for s in TAB_SPECS)}

navigation.search.setText("variables")
navigation.activate_first_match()
report["opened"] = workspace.current_tab_key()
report["listed_open"] = "variables" in {r["key"] for r in workspace.list_registered_tabs() if r["visible"]}
navigation.search.setText("")
workspace.hide_tab("variables")

window._navigation_dock.setVisible(False)
window._search_action.trigger()
report["panel_shown_by_shortcut"] = not window._navigation_dock.isHidden()
report["shortcuts"] = [window._search_action.shortcut().toString(), window._sidebar_action.shortcut().toString()]

window._user_font_pt = 14
window.set_theme("light")
report["light"] = LIGHT.window in window.styleSheet() and font_rule(14) in window.styleSheet()
window.set_theme("dark")
report["dark"] = DARK.window in window.styleSheet() and font_rule(14) in window.styleSheet()
window._user_font_pt = 0
window._apply_font_pt(0)

before = len(window.actions())
window._on_language_changed("English")
window._on_language_changed("English")
report["actions_before"], report["actions_after"] = before, len(window.actions())
report["placeholder"] = navigation.search.placeholderText()
view = next(a.menu() for a in window.menuBar().actions() if a.menu() is not None
            and window._search_action in a.menu().actions())
report["view_menu"] = [a.text() for a in view.actions() if a.text()]

window.resize(640, 420)
app.processEvents()
report["small"] = [window.width(), window.height(), workspace.width(), navigation.isVisible()]
sys.stdout.write(json.dumps(report))
sys.stdout.flush()
os._exit(0)
"""


@pytest.fixture(scope="module")
def window():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    root = pathlib.Path(__file__).resolve().parents[3]
    env = dict(os.environ, PYTHONPATH=str(root), QT_QPA_PLATFORM="offscreen")
    done = subprocess.run([sys.executable, "-c", _PROBE], capture_output=True, text=True,  # nosec B603  # nosemgrep  # reason: fixed argv, no shell
                          timeout=180, env=env, cwd=str(root), check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


def test_search_reaches_every_registered_feature(window):
    assert window["reachable"] == window["registered"] == sorted(spec.key for spec in TAB_SPECS)


def test_choosing_a_feature_opens_it_and_marks_it_open(window):
    assert window["opened"] == "variables" and window["listed_open"]


def test_the_search_shortcut_reveals_a_hidden_panel(window):
    assert window["panel_shown_by_shortcut"]
    assert window["shortcuts"] == ["Ctrl+K", "Ctrl+B"]


def test_switching_theme_keeps_the_text_size(window):
    assert window["light"] and window["dark"]


def test_rebuilding_the_menus_for_a_language_switch_adds_no_shortcut(window):
    assert window["actions_after"] == window["actions_before"]
    assert window["placeholder"]
    assert window["view_menu"] == ["Search Features...", "Navigation Panel", "Tabs", "Theme", "Text Size"]


def test_the_window_shrinks_to_a_small_screen_with_both_panes_usable(window):
    width, height, workspace_width, panel_visible = window["small"]
    assert (width, height) == (640, 420), "the window refused to shrink"
    assert panel_visible and workspace_width >= 300
