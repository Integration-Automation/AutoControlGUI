"""Audit round 3 regression for the Linux X11 hotkey grab (finding 12).

_grab_masked registers a hotkey under several lock-mask variants. If a later
variant fails it must roll back the ones that already succeeded, otherwise the
grab leaks (and _registered is never updated, so every poll re-grabs and spams
BadAccess).

Xlib is not installed on the test host, so a minimal fake module is injected.
"""
import sys
import types

from je_auto_control.utils.hotkey.backends.linux_backend import (
    LinuxHotkeyBackend,
)


def _install_fake_xlib(monkeypatch) -> None:
    fake_x = types.SimpleNamespace(
        GrabModeAsync=1, Mod2Mask=0x10, LockMask=0x02,
    )
    fake_xlib = types.ModuleType("Xlib")
    fake_xlib.X = fake_x
    monkeypatch.setitem(sys.modules, "Xlib", fake_xlib)


def test_grab_masked_rolls_back_on_partial_failure(monkeypatch):
    _install_fake_xlib(monkeypatch)
    binding = types.SimpleNamespace(combo="ctrl+a", binding_id="b1")
    grab_masks = []
    ungrab_masks = []

    class _Root:
        def grab_key(self, keycode, mask, *_args):
            grab_masks.append(mask)
            if len(grab_masks) == 3:  # variants: 0, Mod2, Lock, Mod2|Lock
                raise RuntimeError("BadAccess")

        def ungrab_key(self, keycode, mask):
            ungrab_masks.append(mask)

    ok = LinuxHotkeyBackend._grab_masked(
        _Root(), binding, mask=0x04, keycode=38,
    )

    assert ok is False
    assert grab_masks == [0x04, 0x14, 0x06]  # base | {0, Mod2, Lock}
    # The two grabs that succeeded (extra masks 0 and Mod2) are rolled back.
    assert ungrab_masks == [0x04, 0x14]


def test_grab_masked_returns_true_when_all_variants_succeed(monkeypatch):
    _install_fake_xlib(monkeypatch)
    binding = types.SimpleNamespace(combo="ctrl+a", binding_id="b1")
    ungrab_masks = []

    class _Root:
        def grab_key(self, keycode, mask, *_args):
            pass

        def ungrab_key(self, keycode, mask):
            ungrab_masks.append(mask)

    ok = LinuxHotkeyBackend._grab_masked(
        _Root(), binding, mask=0x04, keycode=38,
    )
    assert ok is True
    assert ungrab_masks == []  # nothing rolled back on full success
