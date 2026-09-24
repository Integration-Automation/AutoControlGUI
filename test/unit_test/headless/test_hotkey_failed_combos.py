"""macOS and Linux hotkey backends do not retry a failed combo on every tick.

A combo the platform cannot take logged an error on every sync, roughly ten
times a second, for as long as the daemon ran -- the Windows backend already
remembered failures. ``bind()`` also validated the key on Windows only.
"""
import types

import pytest

from je_auto_control.utils.hotkey import hotkey_daemon
from je_auto_control.utils.hotkey.backends import linux_backend, macos_backend
from je_auto_control.utils.hotkey.backends.base import FailedCombos
from je_auto_control.utils.hotkey.hotkey_daemon import HotkeyBinding


class _Errors:
    def __init__(self):
        self.count = 0

    def error(self, *_args, **_kwargs):
        self.count += 1


def _binding(combo, binding_id="b1"):
    return HotkeyBinding(binding_id=binding_id, combo=combo, script_path="s.json")


def test_macos_logs_an_unsupported_combo_once(monkeypatch):
    errors = _Errors()
    monkeypatch.setattr(macos_backend, "autocontrol_logger", errors)
    backend = macos_backend.MacOSHotkeyBackend()
    bindings = [_binding("ctrl+.")]
    for _ in range(10):
        backend._sync(bindings)
    assert errors.count == 1
    backend._sync([_binding("ctrl+a")])
    assert "b1" in backend._registered


def test_macos_drops_the_old_combo_when_the_new_one_fails(monkeypatch):
    monkeypatch.setattr(macos_backend, "autocontrol_logger", _Errors())
    backend = macos_backend.MacOSHotkeyBackend()
    backend._sync([_binding("ctrl+a")])
    backend._sync([_binding("ctrl+.")])
    assert "b1" not in backend._registered


class _Root:
    pass


@pytest.mark.parametrize("failure", ["parse", "grab"])
def test_linux_logs_a_failing_combo_once(monkeypatch, failure):
    errors = _Errors()
    monkeypatch.setattr(linux_backend, "autocontrol_logger", errors)
    grabs = []

    def combo_to_x11(combo):
        if failure == "parse":
            raise ValueError(f"unsupported key in {combo!r}")
        return 4, 60

    def grab(_self, _root, binding, _mask, _keycode):
        grabs.append(binding.combo)
        errors.error("XGrabKey failed")
        return False

    monkeypatch.setattr(linux_backend, "_combo_to_x11", combo_to_x11)
    monkeypatch.setattr(linux_backend.LinuxHotkeyBackend, "_grab_masked", grab)
    backend = linux_backend.LinuxHotkeyBackend()
    for _ in range(10):
        backend._sync_one(_Root(), _binding("ctrl+."))
    assert errors.count == 1
    assert len(grabs) == (1 if failure == "grab" else 0)


def test_failures_are_forgotten_with_their_binding():
    failed = FailedCombos()
    failed.record(_binding("ctrl+."))
    assert failed.blocked(_binding("ctrl+."))
    assert not failed.blocked(_binding("ctrl+,"))
    failed.forget_missing([])
    assert not failed.blocked(_binding("ctrl+."))


def test_bind_validates_the_key_on_macos(monkeypatch):
    monkeypatch.setattr(hotkey_daemon, "sys", types.SimpleNamespace(platform="darwin"))
    daemon = hotkey_daemon.HotkeyDaemon(executor=lambda _actions: None)
    with pytest.raises(ValueError):
        daemon.bind("ctrl+.", "s.json")
    assert daemon.bind("ctrl+a", "s.json").combo == "ctrl+a"
