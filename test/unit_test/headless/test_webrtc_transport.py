"""The plumbing both WebRTC ends stand on: bridge, capture, cursor, ICE.

`webrtc_transport` is the module every other WebRTC module imports, and the
one that raises ImportError at module level without aiortc -- so before the
`[webrtc]` extra joined the measured install, nothing here ran on any CI
square at all.

Four things in it are worth pinning down, and none of them need a peer:

* **The bridge is a singleton around one background loop.** `get_bridge()`
  hands the same object to host, viewer and every GUI panel, so `start()`
  has to be idempotent under a lock -- a second loop would silently split
  the DataChannel sends from the PeerConnection they belong to.
* **`_draw_cursor_overlay` writes into a slice of the captured frame.** The
  slice is clamped at the array edges but the circle arithmetic is not, so
  the ring is computed in absolute coordinates and applied to a window that
  may start anywhere. A cursor at the very corner is the case that would
  raise if the two disagreed.
* **`_resolve_monitor` is fed an index that comes from the GUI**, where
  monitors are listed per mss numbering (1-based, 0 = "all"). An index the
  user picked before unplugging a screen must land somewhere real rather
  than raise out of the capture thread.
* **`wait_for_ice_gathering` deliberately gives up.** Its timeout branch is
  the one that ships a half-gathered SDP rather than hanging the offer, and
  it is only reachable when nothing ever completes.

The capture path is exercised against a fake grabber: `_capture_frame`
caches one mss instance per thread in a module-level `threading.local()`,
which is worth a test of its own because a leak there is one screen grabber
per capture rather than one per thread.
"""
from __future__ import annotations

import asyncio
import threading
import time

import numpy as np
import pytest

from headless._webrtc_doubles import FakePeerConnection
from je_auto_control.utils.remote_desktop import webrtc_transport as transport
from je_auto_control.utils.remote_desktop.webrtc_transport import (
    BANDWIDTH_PRESETS, ScreenVideoTrack, WebRTCConfig, _AsyncioBridge,
    _capture_frame, _draw_cursor_overlay, _resolve_monitor, fps_for_preset,
    get_bridge, wait_for_ice_gathering,
)


# --- fakes --------------------------------------------------------------------

class _Grab:
    """What ``mss.grab()`` returns: a BGRA buffer plus its dimensions."""

    def __init__(self, width: int, height: int, fill: int = 7) -> None:
        self.width = width
        self.height = height
        self.bgra = bytes([fill, fill + 1, fill + 2, 255]) * (width * height)


class _FakeSct:
    def __init__(self, monitors=None) -> None:
        self.monitors = monitors if monitors is not None else [
            {"left": 0, "top": 0, "width": 8, "height": 4},
            {"left": 0, "top": 0, "width": 4, "height": 2},
        ]
        self.grabs = []

    def grab(self, monitor):
        self.grabs.append(monitor)
        return _Grab(monitor["width"], monitor["height"])


@pytest.fixture
def fake_grabber(monkeypatch):
    """Install a fake mss grabber and clear the per-thread capture cache."""
    sct = _FakeSct()
    calls = []

    def _grabber():
        calls.append(1)
        return sct

    monkeypatch.setattr(transport, "mss_grabber", _grabber)
    if hasattr(transport._capture_local, "sct"):
        del transport._capture_local.sct
    yield sct, calls
    if hasattr(transport._capture_local, "sct"):
        del transport._capture_local.sct


# --- presets and config -------------------------------------------------------

def test_fps_for_preset_is_case_insensitive_and_falls_back_to_auto():
    assert fps_for_preset("LOW") == BANDWIDTH_PRESETS["low"]["fps"]
    assert fps_for_preset("high") == 30
    # The GUI persists the preset name; a config written by a newer build
    # must not make an older one raise out of the capture setup.
    assert fps_for_preset("ludicrous") == BANDWIDTH_PRESETS["auto"]["fps"]


def test_config_turns_stun_list_into_ice_servers():
    config = WebRTCConfig(ice_servers=["stun:a:1", "stun:b:2"])
    rtc = config.to_rtc_configuration()
    assert [server.urls for server in rtc.iceServers] == ["stun:a:1", "stun:b:2"]


def test_config_appends_turn_server_with_its_credentials():
    config = WebRTCConfig(
        ice_servers=["stun:a:1"], turn_url="turn:relay:3478",
        turn_username="user", turn_credential="secret",
    )
    turn = config.to_rtc_configuration().iceServers[-1]
    assert (turn.urls, turn.username, turn.credential) == (
        "turn:relay:3478", "user", "secret",
    )


def test_config_without_turn_url_adds_no_extra_server():
    config = WebRTCConfig(ice_servers=["stun:a:1"], turn_username="user")
    # Credentials with no URL are half-filled GUI state, not a server.
    assert len(config.to_rtc_configuration().iceServers) == 1


# --- the shared asyncio bridge ------------------------------------------------

def test_bridge_start_is_idempotent_and_runs_submitted_coroutines():
    bridge = _AsyncioBridge()
    try:
        loop = bridge.start()
        assert bridge.start() is loop, "a second loop would split the session"
        assert loop.is_running()

        async def _answer():
            return 42

        assert bridge.submit(_answer()).result(timeout=5.0) == 42
    finally:
        bridge.stop()


def test_bridge_call_soon_runs_the_callable_on_the_loop_thread():
    bridge = _AsyncioBridge()
    seen = {}
    done = threading.Event()

    def _record(value):
        seen["thread"] = threading.current_thread().name
        seen["value"] = value
        done.set()

    try:
        bridge.call_soon(_record, "payload")
        assert done.wait(timeout=5.0)
    finally:
        bridge.stop()
    assert seen["value"] == "payload"
    assert seen["thread"] == "webrtc-loop"


def test_bridge_stop_is_safe_before_start_and_after_stop():
    bridge = _AsyncioBridge()
    bridge.stop()          # never started: nothing to join
    bridge.start()
    bridge.stop()
    bridge.stop()          # already torn down


def test_get_bridge_returns_the_process_wide_instance():
    assert get_bridge() is get_bridge()


# --- cursor overlay -----------------------------------------------------------

def _white(height=48, width=48):
    return np.full((height, width, 3), 255, dtype=np.uint8)


def test_cursor_overlay_draws_a_yellow_ring_around_a_black_core():
    frame = _white()
    _draw_cursor_overlay(frame, 24, 24)
    assert tuple(frame[24, 24]) == (0, 0, 0), "core"
    assert tuple(frame[24, 24 + 8]) == (0, 255, 255), "ring at radius 8"
    assert tuple(frame[0, 0]) == (255, 255, 255), "far corner untouched"


@pytest.mark.parametrize("x,y", [(-1, 10), (10, -1), (48, 10), (10, 48)])
def test_cursor_overlay_ignores_positions_outside_the_frame(x, y):
    frame = _white()
    _draw_cursor_overlay(frame, x, y)
    assert (frame == 255).all(), "an off-screen cursor must not paint"


def test_cursor_overlay_clamps_its_window_at_the_frame_corner():
    # The ring is computed in absolute coordinates and written into a slice
    # that stops at the edge; at (0, 0) three quarters of it are off-frame.
    frame = _white()
    _draw_cursor_overlay(frame, 0, 0)
    assert tuple(frame[0, 0]) == (0, 0, 0)
    assert tuple(frame[0, 8]) == (0, 255, 255)


# --- monitor resolution and capture -------------------------------------------

def test_resolve_monitor_returns_the_requested_entry():
    sct = _FakeSct()
    assert _resolve_monitor(sct, 1) is sct.monitors[1]


@pytest.mark.parametrize("index", [-1, 2, 99])
def test_resolve_monitor_falls_back_to_the_first_screen(index):
    # A stale index (the user unplugged the screen they had picked) must
    # land on a real monitor rather than raise inside the capture thread.
    sct = _FakeSct()
    assert _resolve_monitor(sct, index) is sct.monitors[1]


def test_resolve_monitor_falls_back_to_the_only_entry_when_alone():
    sct = _FakeSct(monitors=[{"left": 0, "top": 0, "width": 2, "height": 2}])
    assert _resolve_monitor(sct, 5) is sct.monitors[0]


def test_resolve_monitor_raises_when_mss_reports_nothing():
    with pytest.raises(RuntimeError, match="no monitors"):
        _resolve_monitor(_FakeSct(monitors=[]), 1)


def test_capture_frame_drops_alpha_and_returns_a_contiguous_bgr_array(
        fake_grabber):
    monitor = {"left": 0, "top": 0, "width": 4, "height": 2}
    arr = _capture_frame(monitor)
    assert arr.shape == (2, 4, 3)
    assert arr.dtype == np.uint8
    # av.VideoFrame.from_ndarray requires contiguity; the BGRA slice is not.
    assert arr.flags["C_CONTIGUOUS"]
    assert tuple(arr[0, 0]) == (7, 8, 9), "the alpha byte is dropped, not read"


def test_capture_frame_reuses_one_grabber_per_thread(fake_grabber):
    sct, calls = fake_grabber
    monitor = {"left": 0, "top": 0, "width": 4, "height": 2}
    _capture_frame(monitor)
    _capture_frame(monitor)
    assert len(calls) == 1, "one mss instance per thread, not per frame"
    assert len(sct.grabs) == 2


# --- ScreenVideoTrack ---------------------------------------------------------

@pytest.fixture
def track_factory():
    """Build ScreenVideoTracks and shut their capture executors down."""
    made = []

    def _make(**kwargs):
        track = ScreenVideoTrack(**kwargs)
        made.append(track)
        return track

    yield _make
    for track in made:
        track.stop()


@pytest.mark.parametrize("requested,expected", [
    (0, 1), (-5, 1), (24, 24), (61, 60), (1000, 60),
])
def test_track_clamps_its_frame_rate(track_factory, requested, expected):
    assert track_factory(fps=requested).fps == expected


def test_set_target_fps_updates_the_period_it_sleeps_on(track_factory):
    track = track_factory(fps=10)
    track.set_target_fps(20)
    assert track.fps == 20
    assert track._period == pytest.approx(0.05)


def test_set_target_fps_ignores_a_repeat_of_the_current_rate(track_factory):
    track = track_factory(fps=24)
    period = track._period
    track.set_target_fps(24)
    assert track._period is period


def test_set_target_fps_clamps_the_adaptive_controller_too(track_factory):
    # The bandwidth controller feeds this from observed RTT, so the clamp
    # is the only thing between a bad measurement and a 1/0 period.
    track = track_factory(fps=24)
    track.set_target_fps(0)
    assert track.fps == 1


def test_track_resolves_a_region_without_asking_mss(track_factory,
                                                    fake_grabber):
    _, calls = fake_grabber
    track = track_factory(region=(10, 20, 30, 40))
    assert track._resolve() == {"left": 10, "top": 20,
                                "width": 30, "height": 40}
    assert not calls, "a fixed region needs no monitor enumeration"


def test_track_resolves_and_caches_the_monitor(track_factory, fake_grabber):
    sct, _ = fake_grabber
    track = track_factory(monitor_index=1)
    assert track._resolve() is sct.monitors[1]
    assert track._resolve() is sct.monitors[1]


def test_set_target_monitor_invalidates_the_cached_lookup(track_factory,
                                                          fake_grabber):
    sct, _ = fake_grabber
    track = track_factory(monitor_index=1)
    track._resolve()
    track.set_target_monitor(0)
    assert track._resolve() is sct.monitors[0]


def test_track_recv_returns_a_bgr_video_frame_with_a_timestamp(
        track_factory, monkeypatch):
    captured = np.full((4, 6, 3), 255, dtype=np.uint8)
    monkeypatch.setattr(transport, "_capture_frame", lambda monitor: captured)
    monkeypatch.setattr(transport, "_get_cursor_position", lambda: None)
    track = track_factory(region=(0, 0, 6, 4), fps=60, show_cursor=True)
    frame = asyncio.run(track.recv())
    assert (frame.width, frame.height) == (6, 4)
    assert frame.time_base is not None
    assert (frame.to_ndarray(format="bgr24") == 255).all()


def test_track_recv_overlays_the_cursor_in_monitor_local_coordinates(
        track_factory, monkeypatch):
    captured = np.full((48, 48, 3), 255, dtype=np.uint8)
    monkeypatch.setattr(transport, "_capture_frame", lambda monitor: captured)
    # Absolute (124, 224) on a monitor pinned at (100, 200) is local (24, 24).
    monkeypatch.setattr(transport, "_get_cursor_position", lambda: (124, 224))
    track = track_factory(region=(100, 200, 48, 48), fps=60)
    frame = asyncio.run(track.recv())
    arr = frame.to_ndarray(format="bgr24")
    assert tuple(arr[24, 24]) == (0, 0, 0)


def test_track_recv_skips_the_overlay_when_the_cursor_is_unknown(
        track_factory, monkeypatch):
    captured = np.full((48, 48, 3), 255, dtype=np.uint8)
    monkeypatch.setattr(transport, "_capture_frame", lambda monitor: captured)
    # Wayland and headless X both leave the position unavailable.
    monkeypatch.setattr(transport, "_get_cursor_position", lambda: None)
    track = track_factory(region=(0, 0, 48, 48), fps=60, show_cursor=True)
    frame = asyncio.run(track.recv())
    assert (frame.to_ndarray(format="bgr24") == 255).all()


def test_track_recv_paces_itself_at_the_target_rate(track_factory,
                                                    monkeypatch):
    # Real time, not a patched `asyncio.sleep`: `transport.asyncio` IS the
    # asyncio module, so patching through it also rewires aiortc's own
    # `next_timestamp`, and the recorded delays stop being ours. 10 fps
    # keeps the whole test inside a tenth of a second.
    captured = np.full((4, 4, 3), 255, dtype=np.uint8)
    monkeypatch.setattr(transport, "_capture_frame", lambda monitor: captured)
    monkeypatch.setattr(transport, "_get_cursor_position", lambda: None)
    track = track_factory(region=(0, 0, 4, 4), fps=10, show_cursor=False)

    started = time.monotonic()
    asyncio.run(track.recv())
    first = time.monotonic() - started
    asyncio.run(track.recv())
    second = time.monotonic() - started - first

    # The first frame goes out immediately; the second waits out the period.
    assert first < 0.05
    assert second >= 0.05


def test_track_stop_shuts_the_capture_executor_down():
    track = ScreenVideoTrack(region=(0, 0, 4, 4))
    track.stop()
    with pytest.raises(RuntimeError):
        track._executor.submit(lambda: None)


# --- ICE gathering ------------------------------------------------------------

def test_wait_for_ice_gathering_returns_at_once_when_already_complete():
    pc = FakePeerConnection()
    pc.iceGatheringState = "complete"
    asyncio.run(wait_for_ice_gathering(pc))
    assert not pc.handlers, "no need to subscribe to a finished gather"


def test_wait_for_ice_gathering_resolves_on_the_state_change():
    pc = FakePeerConnection()

    async def _drive():
        waiter = asyncio.ensure_future(wait_for_ice_gathering(pc, timeout=5.0))
        await asyncio.sleep(0)
        pc.complete_ice_gathering()
        await waiter

    asyncio.run(_drive())


def test_wait_for_ice_gathering_ignores_intermediate_states():
    pc = FakePeerConnection()

    async def _drive():
        waiter = asyncio.ensure_future(wait_for_ice_gathering(pc, timeout=5.0))
        await asyncio.sleep(0)
        pc.iceGatheringState = "gathering"
        pc.handlers["icegatheringstatechange"]()
        assert not waiter.done()
        pc.complete_ice_gathering()
        await waiter

    asyncio.run(_drive())


def test_wait_for_ice_gathering_gives_up_and_sends_what_it_has():
    # The timeout is the branch that ships a half-gathered SDP instead of
    # hanging create_offer() until its own 12 s future times out.
    pc = FakePeerConnection()
    asyncio.run(wait_for_ice_gathering(pc, timeout=0.05))
    assert pc.iceGatheringState == "new"
