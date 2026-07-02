"""GUI smoke tests for the window-level Actions menu tab hooks."""
import os

import pytest

pytest.importorskip("PySide6.QtWidgets")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from je_auto_control.gui.main_widget import AutoControlGUIWidget  # noqa: E402

# Interactive panels that intentionally keep their own in-tab layouts
# instead of exposing commands through the Actions menu.
_MENU_EXEMPT_TABS = {"script_builder", "remote_desktop"}


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(scope="module")
def widget(app):
    return AutoControlGUIWidget()


def _entry_actions(entry):
    if entry.actions:
        return list(entry.actions)
    provider = getattr(entry.widget, "menu_actions", None)
    return list(provider()) if callable(provider) else []


def test_every_tab_exposes_menu_actions(widget):
    missing = [
        entry.key for entry in widget._tab_entries
        if entry.key not in _MENU_EXEMPT_TABS and not _entry_actions(entry)
    ]
    assert missing == []


def test_menu_actions_are_key_handler_pairs(widget):
    for entry in widget._tab_entries:
        for action in _entry_actions(entry):
            label_key, handler = action
            assert isinstance(label_key, str) and label_key
            assert callable(handler)


def test_current_tab_menu_actions_follows_active_tab(widget):
    record_entry = next(
        entry for entry in widget._tab_entries if entry.key == "record"
    )
    widget.tabs.setCurrentWidget(record_entry.widget)
    assert widget.current_tab_menu_actions() == list(record_entry.actions)


def test_hook_tab_actions_reach_the_menu(widget):
    widget.show_tab("variables")
    entry = next(
        entry for entry in widget._tab_entries if entry.key == "variables"
    )
    widget.tabs.setCurrentWidget(entry.widget)
    actions = widget.current_tab_menu_actions()
    assert actions == entry.widget.menu_actions()
    assert actions, "hook-based tab should surface its actions"
