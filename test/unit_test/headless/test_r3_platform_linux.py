"""Round-3 platform regression tests: Linux (Wayland + X11) backends.

Headless — no real input is dispatched and no X server is contacted. The
Wayland helpers are pure bit math; the X11 ``get_pixel`` decode is driven
with a synthetic pixel buffer via ``sys.modules`` stubs so the Linux-only
module imports on any host.

Covers audit findings:
* #3 Wayland ``press_mouse`` must emit a button-down edge only (hold),
  ``release_mouse`` an up edge only.
* #4 X11 ``get_pixel`` must return true ``(R, G, B)``, not raw BGR bytes.
* #6 Wayland listener must expose ``check_key_is_press`` so the
  critical-exit watcher does not ``AttributeError``.
"""
import importlib
import sys
import types

import je_auto_control  # noqa: F401  # load the facade under the real platform first

_DOWN_BIT = 0x40
_UP_BIT = 0x80


def test_finding3_wayland_press_is_down_edge_only():
    """press -> down-bit set / up-bit clear; release -> up-bit set / down clear."""
    from je_auto_control.linux_wayland import mouse as wayland_mouse

    buttons = (
        wayland_mouse.wayland_mouse_left,
        wayland_mouse.wayland_mouse_middle,
        wayland_mouse.wayland_mouse_right,
    )
    for button in buttons:
        press = wayland_mouse._press_code(button)
        release = wayland_mouse._release_code(button)
        # press holds the button: down edge only.
        assert press & _DOWN_BIT
        assert not press & _UP_BIT
        # release lifts the button: up edge only.
        assert release & _UP_BIT
        assert not release & _DOWN_BIT
        # the button selector (low nibble) is preserved in both.
        assert press & 0x0F == button & 0x0F
        assert release & 0x0F == button & 0x0F

    # Concretely for left (0xC0 = down|up of button 0).
    assert wayland_mouse._press_code(0xC0) == 0x40
    assert wayland_mouse._release_code(0xC0) == 0x80


def test_finding6_wayland_listener_has_check_key_is_press():
    """The name must exist (best-effort False) so callers degrade, not crash."""
    from je_auto_control.linux_wayland import listener

    assert hasattr(listener, "check_key_is_press")
    assert "check_key_is_press" in listener.__all__
    # positional (critical-exit) and keyword (wrapper) call styles both work.
    assert listener.check_key_is_press(65) is False
    assert listener.check_key_is_press(keycode=65) is False


def test_finding4_x11_get_pixel_returns_rgb(monkeypatch):
    """A little-endian BGRX buffer must decode to (R, G, B)."""
    monkeypatch.setattr(sys, "platform", "linux")

    fake_xlib = types.ModuleType("Xlib")
    fake_xlib.X = types.SimpleNamespace(ZPixmap=2)
    monkeypatch.setitem(sys.modules, "Xlib", fake_xlib)

    class _FakeImage:
        # bytes on the wire: Blue, Green, Red, unused.
        data = bytes([0x10, 0x20, 0x30, 0xFF])

    class _FakeRoot:
        def get_image(self, *_args, **_kwargs):
            return _FakeImage()

    class _FakeScreen:
        root = _FakeRoot()
        width_in_pixels = 100
        height_in_pixels = 100

    class _FakeDisplay:
        def screen(self):
            return _FakeScreen()

    display_mod = types.ModuleType("x11_linux_display")
    display_mod.display = _FakeDisplay()
    monkeypatch.setitem(
        sys.modules,
        "je_auto_control.linux_with_x11.core.utils.x11_linux_display",
        display_mod,
    )
    monkeypatch.delitem(
        sys.modules,
        "je_auto_control.linux_with_x11.screen.x11_linux_screen",
        raising=False,
    )

    screen_mod = importlib.import_module(
        "je_auto_control.linux_with_x11.screen.x11_linux_screen"
    )
    # Blue=0x10, Green=0x20, Red=0x30 -> (R, G, B) = (0x30, 0x20, 0x10).
    assert screen_mod.get_pixel(0, 0) == (0x30, 0x20, 0x10)
    assert screen_mod._decode_pixel(bytes([1, 2, 3, 4])) == (3, 2, 1)
