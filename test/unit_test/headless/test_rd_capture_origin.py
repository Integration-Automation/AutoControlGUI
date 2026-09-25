"""Remote input and the broadcast cursor use the captured frame's coordinates.

A viewer clicks in the frame it sees; the hosts passed those coordinates to
set_mouse_position as screen positions. A frame whose top-left is not (0, 0)
-- a second monitor, a region, or a virtual desktop reaching above the
primary screen (the legacy host's default) -- put every click that far off,
and the legacy host broadcast the cursor in screen coordinates.
"""
import types

import pytest

from je_auto_control.utils.remote_desktop import host_capture, input_dispatch
from je_auto_control.utils.remote_desktop.input_dispatch import InputDispatchError, dispatch_input

_ORIGIN = (1920, -164)


@pytest.fixture()
def calls(monkeypatch):
    recorded = []

    def make(name):
        return lambda *args, **kwargs: recorded.append((name, args))

    fake = {name: make(name) for name in (
        "click_mouse", "mouse_scroll", "press_mouse", "release_mouse", "set_mouse_position",
        "press_keyboard_key", "release_keyboard_key", "write")}
    fake["get_mouse_position"] = lambda: (1930, -144)
    monkeypatch.setattr(input_dispatch, "_import_wrappers", lambda: fake)
    return recorded


def test_absolute_positions_are_moved_by_the_origin(calls):
    dispatch_input({"action": "mouse_move", "x": 10, "y": 20}, origin=_ORIGIN)
    dispatch_input({"action": "mouse_click", "x": 10, "y": 20}, origin=_ORIGIN)
    dispatch_input({"action": "mouse_scroll", "x": 10, "y": 20, "amount": 1}, origin=_ORIGIN)
    dispatch_input({"action": "mouse_move_relative", "dx": 5, "dy": 5}, origin=_ORIGIN)
    assert calls == [("set_mouse_position", (1930, -144)), ("set_mouse_position", (1930, -144)),
                     ("click_mouse", ("mouse_left",)), ("mouse_scroll", (1, 1930, -144)),
                     ("set_mouse_position", (1935, -139))]


def test_a_bad_coordinate_is_still_a_dispatch_error(calls):
    with pytest.raises(InputDispatchError):
        dispatch_input({"action": "mouse_move", "x": "left", "y": 20}, origin=_ORIGIN)
    assert calls == []


def test_the_capture_origin_is_the_region_or_the_virtual_desktop(monkeypatch):
    assert host_capture.capture_origin([1920, -164, 1920, 1080]) == _ORIGIN
    monkeypatch.setattr(host_capture, "list_host_monitors",
                        lambda: [{"left": 0, "top": -164}, {"left": 0, "top": 0}])
    assert host_capture.capture_origin(None) == (0, -164)
    monkeypatch.setattr(host_capture, "list_host_monitors", lambda: [])
    assert host_capture.capture_origin(None) == (0, 0)


def test_the_legacy_host_maps_input_and_the_cursor_through_its_region(calls, monkeypatch):
    from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost
    from je_auto_control.wrapper import auto_control_mouse
    monkeypatch.setattr(auto_control_mouse, "get_mouse_position", lambda: (1930, -144))
    host = RemoteDesktopHost(token="t", region=[1920, -164, 1920, 1080])
    host._dispatch({"action": "mouse_move", "x": 10, "y": 20})
    assert calls == [("set_mouse_position", (1930, -144))]
    assert host._cursor_provider() == (10, 20)


def test_the_webrtc_hosts_dispatch_by_their_track_origin(calls):
    pytest.importorskip("aiortc")
    pytest.importorskip("av")
    from je_auto_control.utils.remote_desktop.multi_viewer import MultiViewerHost
    from je_auto_control.utils.remote_desktop.webrtc_host import WebRTCDesktopHost
    from je_auto_control.utils.remote_desktop.webrtc_transport import ScreenVideoTrack
    track = ScreenVideoTrack(region=[1920, -164, 1920, 1080])
    single = WebRTCDesktopHost(token="t")
    single._video_track = track
    single._dispatch({"action": "mouse_move", "x": 10, "y": 20})
    multi = MultiViewerHost(token="t")
    multi._source = types.SimpleNamespace(capture_origin=track.capture_origin)
    multi._dispatch({"action": "mouse_move", "x": 1, "y": 2})
    assert calls == [("set_mouse_position", (1930, -144)), ("set_mouse_position", (1921, -162))]
    track.stop()


def test_a_host_without_a_display_still_starts(monkeypatch):
    class ScreenShotError(Exception):
        """mss's own error type, which is no OSError."""

    def no_display():
        raise ScreenShotError("$DISPLAY not set")

    monkeypatch.setattr(host_capture, "list_host_monitors", no_display)
    assert host_capture.capture_origin(None) == (0, 0)
