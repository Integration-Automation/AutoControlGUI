"""Tests for the hotkey backend abstraction."""
import threading
import time

import pytest

from je_auto_control.utils.hotkey import backends as backends_pkg
from je_auto_control.utils.hotkey.backends.base import HotkeyBackend
from je_auto_control.utils.hotkey.backends.linux_backend import (
    LinuxHotkeyBackend,
)
from je_auto_control.utils.hotkey.backends.macos_backend import (
    MacOSHotkeyBackend, _combo_to_macos, _primary_key_to_keycode,
)
from je_auto_control.utils.hotkey.hotkey_daemon import (
    BackendContext, HotkeyDaemon, split_combo,
)


def test_split_combo_canonicalises_aliases():
    mods_win, key = split_combo("win+a")
    mods_super, _ = split_combo("super+a")
    mods_meta, _ = split_combo("meta+a")
    assert mods_win == mods_super == mods_meta == frozenset({"win"})
    assert key == "a"


def test_split_combo_mixed_modifiers():
    mods, key = split_combo("CTRL + alt + Shift + F7")
    assert mods == frozenset({"ctrl", "alt", "shift"})
    assert key == "f7"


def test_split_combo_rejects_empty():
    with pytest.raises(ValueError):
        split_combo("")


def test_split_combo_rejects_modifier_only():
    with pytest.raises(ValueError):
        split_combo("ctrl+alt")


class _FakeBackend(HotkeyBackend):
    name = "fake"

    def __init__(self):
        self.ran = threading.Event()
        self.last_bindings = None

    def run_forever(self, context: BackendContext) -> None:
        self.last_bindings = context.get_bindings()
        # Simulate firing the first registered binding, if any.
        if self.last_bindings:
            context.fire(self.last_bindings[0].binding_id)
        self.ran.set()
        context.stop_event.wait(0.5)


def test_daemon_routes_through_backend(monkeypatch):
    fake = _FakeBackend()
    monkeypatch.setattr(backends_pkg, "get_backend", lambda: fake)
    called = []
    daemon = HotkeyDaemon(executor=lambda actions: called.append(actions))
    # Provide bindings + stub read_action_json so _fire_binding finishes.
    from je_auto_control.utils.hotkey import hotkey_daemon as mod
    monkeypatch.setattr(mod, "read_action_json", lambda path: [["AC_noop"]])
    binding = daemon.bind("ctrl+alt+1", "script.json")
    try:
        daemon.start()
        assert fake.ran.wait(timeout=2.0), "backend run_forever should have started"
        time.sleep(0.05)
    finally:
        daemon.stop(timeout=1.0)
    assert binding.fired == 1
    assert called, "executor should have been invoked by the fake backend"


def test_daemon_snapshot_returns_current_bindings():
    daemon = HotkeyDaemon(executor=lambda _: None)
    daemon.bind("ctrl+a", "x.json", binding_id="b1")
    daemon.bind("ctrl+b", "y.json", binding_id="b2")
    ids = sorted(b.binding_id for b in daemon._snapshot())
    assert ids == ["b1", "b2"]


def test_macos_combo_conversion_covers_modifiers_and_primary():
    mask, keycode = _combo_to_macos("ctrl+shift+alt+win+A")
    # letter "a" on macOS has keycode 0
    assert keycode == 0
    # All four modifier flags set
    assert mask == (1 << 17) | (1 << 18) | (1 << 19) | (1 << 20)


def test_macos_primary_key_unsupported():
    with pytest.raises(ValueError):
        _primary_key_to_keycode("not-a-real-key")


def test_macos_function_keys():
    assert _primary_key_to_keycode("f5") == 96
    assert _primary_key_to_keycode("F12") == 111


def test_macos_digits():
    assert _primary_key_to_keycode("0") == 29
    assert _primary_key_to_keycode("5") == 23


def test_backends_have_distinct_names():
    names = {
        LinuxHotkeyBackend.name,
        MacOSHotkeyBackend.name,
    }
    # Importing the Windows backend on non-Windows is fine because it only
    # calls ctypes.WinDLL inside run_forever, not at import time.
    from je_auto_control.utils.hotkey.backends.windows_backend import (
        WindowsHotkeyBackend,
    )
    names.add(WindowsHotkeyBackend.name)
    assert names == {"windows", "linux-x11", "macos"}
