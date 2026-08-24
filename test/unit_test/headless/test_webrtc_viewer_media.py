"""Attaching the viewer's own screen and microphone to the host's slots.

Split out of `test_webrtc_viewer_session.py`, which covers the offer/answer
exchange this rides on. Everything here turns on one upstream fact and one
design decision:

* **Slots are identified by m-line order, not by direction.** aiortc gives
  every answerer transceiver the default `recvonly` direction regardless of
  what the offer asked for, so the viewer cannot filter by direction and
  counts instead: the *second* video transceiver is the host's recvonly
  slot, because the first is the host's own outbound screen. Off by one
  there and the viewer replaces the picture it is here to watch.
* **OFF is in-place; ON renegotiates.** Turning a stream off is
  `replaceTrack(None)` plus a stop, keeping the SDP direction so the slot
  survives -- the host simply sees its consume task end. Turning one on
  always needs a fresh `track` event at the host, so it costs a
  renegotiation round trip. Getting that backwards costs one on every mute.

The doubles come from `headless._webrtc_doubles`; what is not faked is the
slot arithmetic, which is the thing under test.
"""
from __future__ import annotations

import asyncio

import pytest

from headless._webrtc_doubles import (
    Bridge, Channel, FakePeerConnection, Track, Transceiver,
    noop_ice_gathering,
)
from je_auto_control.utils.remote_desktop import webrtc_viewer as viewer_module
from je_auto_control.utils.remote_desktop.webrtc_transport import WebRTCConfig
from je_auto_control.utils.remote_desktop.webrtc_viewer import (
    WebRTCDesktopViewer,
)


@pytest.fixture(autouse=True)
def fake_peer_connection(monkeypatch):
    FakePeerConnection.instances = []
    monkeypatch.setattr(viewer_module, "RTCPeerConnection", FakePeerConnection)
    monkeypatch.setattr(viewer_module, "wait_for_ice_gathering",
                        noop_ice_gathering)
    yield
    FakePeerConnection.instances = []


@pytest.fixture(autouse=True)
def bridge(monkeypatch):
    fake = Bridge()
    monkeypatch.setattr(viewer_module, "get_bridge", lambda: fake)
    return fake


@pytest.fixture
def screen_track(monkeypatch):
    """Replace the capture the viewer attaches when it shares its screen."""
    made = []

    def _factory(**kwargs):
        track = Track("video")
        track.kwargs = kwargs
        made.append(track)
        return track

    monkeypatch.setattr(
        "je_auto_control.utils.remote_desktop.webrtc_transport"
        ".ScreenVideoTrack", _factory,
    )
    return made


@pytest.fixture
def opus_track(monkeypatch):
    made = []

    def _factory():
        track = Track("audio")
        made.append(track)
        return track

    monkeypatch.setattr(
        "je_auto_control.utils.remote_desktop.webrtc_audio.OpusMicAudioTrack",
        _factory,
    )
    return made


def _viewer(**kwargs) -> WebRTCDesktopViewer:
    kwargs.setdefault("token", "secret")
    return WebRTCDesktopViewer(**kwargs)


def _connected(**kwargs):
    """A viewer with a peer connection already in place."""
    viewer = _viewer(**kwargs)
    viewer._pc = FakePeerConnection()
    return viewer, viewer._pc


# --- attaching the viewer's own media -----------------------------------------

def _video_slots(pc, count=2):
    pc.transceivers = [Transceiver("video") for _ in range(count)]
    return pc.transceivers


def test_sharing_a_screen_takes_the_second_video_slot(screen_track):
    # The first video m-line is the host's outbound screen; taking it would
    # replace the picture the viewer is here to watch.
    viewer = _viewer(config=WebRTCConfig(share_my_screen=True))
    viewer.process_offer("v=0 host-offer")
    pc = FakePeerConnection.instances[0]
    assert pc.transceivers == []          # no slots offered
    viewer._pc = pc
    first, second = _video_slots(pc)
    viewer._attach_viewer_screen_track()
    assert second.sender.track is screen_track[0]
    assert second.direction == "sendonly"
    assert first.sender.track is None


def test_sharing_a_screen_uses_the_viewers_own_capture_settings(screen_track):
    config = WebRTCConfig(share_my_screen=True, monitor_index=2, fps=12,
                          region=(1, 2, 3, 4), show_cursor=False)
    viewer, pc = _connected(config=config)
    _video_slots(pc)
    viewer._attach_viewer_screen_track()
    assert screen_track[0].kwargs == {
        "monitor_index": 2, "fps": 12, "region": (1, 2, 3, 4),
        "show_cursor": False,
    }


def test_sharing_a_screen_the_host_never_offered_is_a_warning_not_a_crash(
        screen_track):
    # `accept_viewer_video=False` on the host means there is no second slot;
    # the viewer must keep watching rather than raise out of the answer.
    viewer, pc = _connected(config=WebRTCConfig(share_my_screen=True))
    _video_slots(pc, count=1)
    viewer._attach_viewer_screen_track()
    assert viewer._viewer_screen_track is None
    assert screen_track == []


def test_sharing_a_microphone_takes_the_only_audio_slot(opus_track):
    viewer, pc = _connected(config=WebRTCConfig(share_my_audio_opus=True))
    slot = Transceiver("audio")
    pc.transceivers = [Transceiver("video"), slot]
    viewer._attach_opus_audio_track()
    assert slot.sender.track is opus_track[0]
    assert slot.direction == "sendonly"


def test_sharing_a_microphone_the_host_never_offered_is_survivable(opus_track):
    viewer, pc = _connected(config=WebRTCConfig(share_my_audio_opus=True))
    pc.transceivers = [Transceiver("video")]
    viewer._attach_opus_audio_track()
    assert viewer._opus_audio_track is None


def test_a_viewer_with_no_microphone_still_answers(monkeypatch):
    def _no_device():
        raise OSError("no input device")

    monkeypatch.setattr(
        "je_auto_control.utils.remote_desktop.webrtc_audio.OpusMicAudioTrack",
        _no_device,
    )
    viewer, pc = _connected(config=WebRTCConfig(share_my_audio_opus=True))
    pc.transceivers = [Transceiver("audio")]
    viewer._attach_opus_audio_track()
    assert viewer._opus_audio_track is None


def test_the_answer_attaches_both_streams_the_config_asks_for(screen_track,
                                                              opus_track):
    config = WebRTCConfig(share_my_screen=True, share_my_audio_opus=True)
    viewer = _viewer(config=config)

    class _PcWithSlots(FakePeerConnection):
        def __init__(self, configuration=None) -> None:
            super().__init__(configuration)
            self.transceivers = [Transceiver("video"), Transceiver("video"),
                                 Transceiver("audio")]

    viewer_module.RTCPeerConnection = _PcWithSlots
    try:
        viewer.process_offer("v=0 host-offer")
    finally:
        viewer_module.RTCPeerConnection = FakePeerConnection
    assert viewer._viewer_screen_track is screen_track[0]
    assert viewer._opus_audio_track is opus_track[0]


# --- live toggles -------------------------------------------------------------

def test_turning_screen_share_on_asks_the_host_to_renegotiate():
    viewer, _ = _connected()
    channel = Channel()
    viewer._control_channel = channel
    viewer.toggle_share_screen(True)
    assert viewer._config.share_my_screen is True
    assert '"renegotiate_request"' in channel.sent[0]


def test_turning_screen_share_on_twice_costs_one_renegotiation():
    viewer, _ = _connected()
    channel = Channel()
    viewer._control_channel = channel
    viewer._viewer_screen_track = Track("video")
    viewer.toggle_share_screen(True)
    assert channel.sent == [], "already sharing"


def test_turning_screen_share_off_detaches_in_place():
    # OFF costs nothing: the SDP direction stays, so the slot survives and
    # the host simply sees its consume task end.
    viewer, pc = _connected()
    channel = Channel()
    viewer._control_channel = channel
    track = Track("video")
    viewer._viewer_screen_track = track
    pc.transceivers = [Transceiver("video", track=track)]
    viewer.toggle_share_screen(False)
    assert track.stopped
    assert pc.transceivers[0].sender.replaced == [None]
    assert viewer._viewer_screen_track is None
    assert channel.sent == [], "no renegotiation on the way down"


def test_turning_the_microphone_off_detaches_in_place():
    viewer, pc = _connected()
    track = Track("audio")
    viewer._opus_audio_track = track
    pc.transceivers = [Transceiver("audio", track=track)]
    viewer.toggle_opus_mic(False)
    assert track.stopped
    assert viewer._opus_audio_track is None


def test_turning_the_microphone_on_asks_the_host_to_renegotiate():
    viewer, _ = _connected()
    channel = Channel()
    viewer._control_channel = channel
    viewer.toggle_opus_mic(True)
    assert viewer._config.share_my_audio_opus is True
    assert '"renegotiate_request"' in channel.sent[0]


def test_turning_the_microphone_on_twice_costs_one_renegotiation():
    viewer, _ = _connected()
    channel = Channel()
    viewer._control_channel = channel
    viewer._opus_audio_track = Track("audio")
    viewer.toggle_opus_mic(True)
    assert channel.sent == []


def test_detaching_skips_transceivers_that_hold_a_different_track():
    # Two video slots and only one of them is ours; the other is the host's
    # screen, and detaching it would blank the window.
    viewer, pc = _connected()
    ours = Track("video")
    theirs = Transceiver("video", track=Track("video"))
    mine = Transceiver("video", track=ours)
    pc.transceivers = [theirs, mine]
    viewer._viewer_screen_track = ours
    viewer.toggle_share_screen(False)
    assert theirs.sender.replaced == []
    assert mine.sender.replaced == [None]


def test_detaching_ignores_transceivers_of_the_other_kind():
    viewer, pc = _connected()
    track = Track("audio")
    audio_slot = Transceiver("audio", track=track)
    pc.transceivers = [Transceiver("video", track=track), audio_slot]
    viewer._opus_audio_track = track
    viewer.toggle_opus_mic(False)
    assert audio_slot.sender.replaced == [None]


def test_a_track_the_connection_no_longer_carries_is_still_stopped():
    # Renegotiation can replace the transceiver set underneath us; the
    # capture thread has to be stopped even when its slot has gone.
    viewer, pc = _connected()
    ours = Track("video")
    pc.transceivers = [Transceiver("video", track=Track("video"))]
    viewer._viewer_screen_track = ours
    viewer.toggle_share_screen(False)
    assert ours.stopped
    assert viewer._viewer_screen_track is None


def test_detaching_a_track_that_was_never_attached_is_a_no_op():
    viewer, pc = _connected()
    pc.transceivers = [Transceiver("video")]
    viewer.toggle_share_screen(False)
    assert pc.transceivers[0].sender.replaced == []


def test_detaching_without_a_peer_connection_is_a_no_op():
    viewer = _viewer()
    viewer._viewer_screen_track = Track("video")
    viewer.toggle_share_screen(False)
    assert viewer._viewer_screen_track is not None, "nothing to detach from"


def test_a_sender_that_rejects_the_detach_still_stops_the_capture():
    # A PeerConnection torn down underneath us fails `replaceTrack`; the
    # capture thread must still be stopped or it runs until the process ends.
    viewer, pc = _connected()
    track = Track("video")
    slot = Transceiver("video", track=track)
    slot.sender.replace_error = RuntimeError("connection closed")
    pc.transceivers = [slot]
    viewer._viewer_screen_track = track
    viewer.toggle_share_screen(False)
    assert track.stopped
    assert viewer._viewer_screen_track is None


def test_a_capture_that_fails_to_stop_is_still_forgotten():
    viewer, pc = _connected()

    class _StubbornTrack(Track):
        def stop(self):
            raise OSError("device gone")

    track = _StubbornTrack("video")
    pc.transceivers = [Transceiver("video", track=track)]
    viewer._viewer_screen_track = track
    viewer.toggle_share_screen(False)
    assert viewer._viewer_screen_track is None


# --- host-initiated renegotiation ---------------------------------------------

def test_a_renegotiation_offer_is_answered_over_the_control_channel():
    viewer, pc = _connected()
    channel = Channel()
    viewer._control_channel = channel
    asyncio.run(viewer._async_handle_renegotiate("v=0 new-offer"))
    assert pc.remote_descriptions[0].type == "offer"
    assert '"renegotiate_answer"' in channel.sent[0]
    assert "v=0 local-sdp" in channel.sent[0]


def test_a_renegotiation_attaches_the_media_the_toggles_asked_for(
        screen_track, opus_track):
    config = WebRTCConfig(share_my_screen=True, share_my_audio_opus=True)
    viewer, pc = _connected(config=config)
    viewer._control_channel = Channel()
    pc.transceivers = [Transceiver("video"), Transceiver("video"),
                       Transceiver("audio")]
    asyncio.run(viewer._async_handle_renegotiate("v=0 new-offer"))
    assert viewer._viewer_screen_track is screen_track[0]
    assert viewer._opus_audio_track is opus_track[0]


def test_a_renegotiation_does_not_re_attach_media_already_sending(
        screen_track):
    viewer, pc = _connected(config=WebRTCConfig(share_my_screen=True))
    viewer._control_channel = Channel()
    existing = Track("video")
    viewer._viewer_screen_track = existing
    pc.transceivers = [Transceiver("video"), Transceiver("video")]
    asyncio.run(viewer._async_handle_renegotiate("v=0 new-offer"))
    assert viewer._viewer_screen_track is existing
    assert screen_track == []


def test_a_renegotiation_aiortc_rejects_sends_no_answer():
    viewer, pc = _connected()
    channel = Channel()
    viewer._control_channel = channel
    pc.answer_error = RuntimeError("invalid SDP")
    asyncio.run(viewer._async_handle_renegotiate("v=0 nonsense"))
    assert channel.sent == [], "a half-built answer is worse than none"


def test_a_renegotiation_without_a_peer_connection_is_a_no_op():
    asyncio.run(_viewer()._async_handle_renegotiate("v=0 new-offer"))
