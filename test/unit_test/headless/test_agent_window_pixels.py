"""Window-only capture and hit testing use fake Win32 APIs, never the desktop."""
import ctypes
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentTaskError


class FakeWindows:
    def __init__(self, *, printed=True):
        self.calls = []
        self.printed = printed
        self.selected = 40

    def GetWindowRect(self, hwnd, pointer):
        assert hwnd == 10
        pointer._obj.left, pointer._obj.top = -20, 30
        pointer._obj.right, pointer._obj.bottom = -18, 31
        return 1

    def IsIconic(self, _hwnd):
        return 0

    def GetWindowDC(self, hwnd):
        assert hwnd == 10
        return 20

    def CreateCompatibleDC(self, dc):
        assert dc == 20
        return 30

    def CreateCompatibleBitmap(self, dc, width, height):
        assert (dc, width, height) == (20, 2, 1)
        return 50

    def SelectObject(self, dc, bitmap):
        assert dc == 30
        self.calls.append(("select", bitmap))
        old, self.selected = self.selected, bitmap
        return old

    def PatBlt(self, *args):
        self.calls.append(("clear", args))
        return 1

    def PrintWindow(self, hwnd, dc, flags):
        assert (hwnd, dc, flags) == (10, 30, 2)
        self.calls.append(("print",))
        return int(self.printed)

    def GetDIBits(self, dc, bitmap, start, height, data, header, usage):
        assert (dc, bitmap, start, height, usage) == (30, 50, 0, 1, 0)
        assert self.selected == 40
        assert header._obj.biHeight == -1
        self.calls.append(("read",))
        ctypes.memmove(data, b"\x00\x00\xff\x00\x00\xff\x00\x00", 8)
        return 1

    def DeleteObject(self, bitmap):
        self.calls.append(("delete bitmap", bitmap))

    def DeleteDC(self, dc):
        self.calls.append(("delete dc", dc))

    def ReleaseDC(self, hwnd, dc):
        self.calls.append(("release", hwnd, dc))


def test_capture_reads_only_the_owned_window_and_restores_gdi_objects(monkeypatch):
    from je_auto_control.utils.agent_runtime import window_pixels
    api = FakeWindows()
    monkeypatch.setattr(window_pixels, "_libraries", lambda: (api, api))
    image, origin = window_pixels.capture_window(10)
    assert origin == (-20, 30)
    assert image.size == (2, 1)
    assert [image.getpixel((x, 0)) for x in range(2)] == [(255, 0, 0), (0, 255, 0)]
    assert [item[0] for item in api.calls] == [
        "select", "clear", "print", "select", "read", "delete dc", "delete bitmap", "release"]


def test_failed_window_render_cleans_resources_without_screen_fallback(monkeypatch):
    from je_auto_control.utils.agent_runtime import window_pixels
    api = FakeWindows(printed=False)
    monkeypatch.setattr(window_pixels, "_libraries", lambda: (api, api))
    with pytest.raises(AgentTaskError, match="render"):
        window_pixels.capture_window(10)
    assert "read" not in [item[0] for item in api.calls]
    assert api.calls[-4:] == [("select", 40), ("delete dc", 30), ("delete bitmap", 50), ("release", 10, 20)]


@pytest.mark.parametrize("failure", ["PatBlt", "GetDIBits", "CreateCompatibleBitmap"])
def test_partial_capture_failures_release_the_window_dc(monkeypatch, failure):
    from je_auto_control.utils.agent_runtime import window_pixels
    api = FakeWindows()
    monkeypatch.setattr(api, failure, lambda *_args: 0)
    monkeypatch.setattr(window_pixels, "_libraries", lambda: (api, api))
    with pytest.raises(AgentTaskError):
        window_pixels.capture_window(10)
    assert api.calls[-1] == ("release", 10, 20)
    assert ("delete dc", 30) in api.calls


def test_moved_window_during_capture_invalidates_its_pixels(monkeypatch):
    from je_auto_control.utils.agent_runtime import window_pixels
    api = FakeWindows()
    monkeypatch.setattr(window_pixels, "_libraries", lambda: (api, api))
    frames = iter([(-20, 30, 2, 1), (-19, 30, 2, 1)])
    monkeypatch.setattr(window_pixels, "_geometry", lambda *_args: next(frames))
    with pytest.raises(AgentTaskError, match="changed"):
        window_pixels.capture_window(10)
    assert api.calls[-1] == ("release", 10, 20)


@pytest.mark.parametrize("hit", [None, 11])
def test_foreign_overlay_inside_owned_rectangle_is_rejected(monkeypatch, hit):
    from je_auto_control.utils.agent_runtime import native_scope
    from je_auto_control.utils.window_capture import window_capture
    monkeypatch.setattr(native_scope.sys, "platform", "win32")
    monkeypatch.setattr(window_capture, "_win32_geometry", lambda _hwnd: (0, 0, 100, 100))
    monkeypatch.setattr(native_scope, "_point_window", lambda _x, _y: hit)
    with pytest.raises(AgentTaskError, match="covered|target"):
        native_scope.check_pointer(10, {"x": 50, "y": 50})


def test_owned_child_window_hit_is_allowed(monkeypatch):
    from je_auto_control.utils.agent_runtime import native_scope
    from je_auto_control.utils.window_capture import window_capture
    monkeypatch.setattr(native_scope.sys, "platform", "win32")
    monkeypatch.setattr(window_capture, "_win32_geometry", lambda _hwnd: (0, 0, 100, 100))
    monkeypatch.setattr(native_scope, "_point_window", lambda _x, _y: 10)
    native_scope.check_pointer(10, {"x": 50, "y": 50})


def test_point_hit_test_uses_pointer_sized_handles(monkeypatch):
    from je_auto_control.utils.agent_runtime import native_scope
    calls = []

    def window_from_point(point):
        calls.append((point.x, point.y))
        return 123

    api = SimpleNamespace(WindowFromPoint=window_from_point,
                          GetAncestor=lambda handle, kind: calls.append((handle, kind)) or 456)
    monkeypatch.setattr(native_scope, "_hit_library", lambda: api)
    assert native_scope._point_window(-20, 30) == 456
    assert calls == [(-20, 30), (123, 2)]
