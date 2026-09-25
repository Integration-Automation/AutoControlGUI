"""Key names given to the file-dialog and popup-watchdog helpers are resolved per platform.

Their defaults and documented examples ("enter", "esc") are not names the
Windows key table knows ("return", "escape"), so the keystroke failed there.
"""
import pytest

from je_auto_control.utils.cua_action import cua_action
from je_auto_control.utils.file_dialog.file_dialog import FileDialogDriver
from je_auto_control.utils.watchdog import popup_watchdog
from je_auto_control.wrapper import auto_control_keyboard

_WIN32 = {"return": 1, "escape": 1}


@pytest.fixture
def typed(monkeypatch):
    keys = []
    monkeypatch.setattr(cua_action, "_platform_key_table", lambda: _WIN32)
    monkeypatch.setattr(auto_control_keyboard, "type_keyboard", keys.append)
    return keys


def test_the_file_dialog_confirm_key_is_resolved(typed):
    FileDialogDriver().confirm("enter")
    assert typed == ["return"]


def test_a_watchdog_key_action_is_resolved(typed, monkeypatch):
    from types import SimpleNamespace

    from je_auto_control.wrapper import auto_control_window, window_backends
    # The key goes to the popup, brought to the front first.
    monkeypatch.setattr(auto_control_window, "find_window", lambda *a, **k: (7, "Popup"))
    monkeypatch.setattr(window_backends, "get_backend",
                        lambda: SimpleNamespace(bring_to_front=lambda window_id: window_id == 7))
    popup_watchdog._window_action("Popup", "esc", False)()
    assert typed == ["escape"]
