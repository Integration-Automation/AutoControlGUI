"""Answering a host's offer, watching what arrives, and letting go.

`WebRTCDesktopViewer` is the offer-consumer half of the pair. Like the host
it needs aiortc to import at all, so nothing here ran on a CI square before
the `[webrtc]` extra joined the measured install. It is split three ways:
the media it attaches to the host's slots is in
`test_webrtc_viewer_media.py`, the control channel in
`test_webrtc_viewer_control.py`, and this file has the session around them.

Three things here are load-bearing well beyond their size:

* **The fingerprint is checked before any DTLS handshake.** That check is
  the whole value of the pinning feature -- a signaling slot that has been
  hijacked has to be caught while the offer is still text, not after
  encrypted bytes are flowing, so a mismatch must not even build a
  PeerConnection.
* **Inbound channels are routed by label**, and the control channel may
  arrive already open. aiortc fires "datachannel" whenever it likes; if the
  channel is open by then, "open" never fires again and an authentication
  handshake that waited for it would wait forever.
* **The frame pump has to end quietly.** Nobody awaits it, so every way a
  track can stop -- the host ending its share, the transport failing, the
  viewer closing -- is a path that must not leave an exception behind.

The doubles come from `headless._webrtc_doubles`.
"""
from __future__ import annotations

import asyncio

import pytest

from headless._webrtc_doubles import (
    Bridge, Channel, FakePeerConnection, FrameTrack, HangingBridge,
    Stoppable, Track, noop_ice_gathering,
)
from je_auto_control.utils.remote_desktop import webrtc_viewer as viewer_module
from je_auto_control.utils.remote_desktop.fingerprint import (
    FingerprintMismatchError,
)
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


# --- construction -------------------------------------------------------------

def test_a_viewer_without_a_token_is_refused():
    with pytest.raises(ValueError, match="non-empty token"):
        WebRTCDesktopViewer(token="")


def test_a_fresh_viewer_reports_no_session():
    viewer = _viewer()
    assert viewer.authenticated is False
    assert viewer.read_only is False
    assert viewer.host_fingerprint is None
    assert viewer.connection_state == "closed"


def test_asking_for_the_peer_connection_before_connecting_is_an_error():
    with pytest.raises(RuntimeError, match="connect first"):
        _viewer()._require_pc()


# --- processing the offer -----------------------------------------------------

@pytest.mark.parametrize("offer", ["", "   "])
def test_an_empty_offer_is_refused_before_it_reaches_aiortc(offer):
    with pytest.raises(ValueError, match="offer_sdp is empty"):
        _viewer().process_offer(offer)


def test_processing_an_offer_returns_the_answer_sdp():
    assert _viewer().process_offer("v=0 host-offer") == "v=0 local-sdp"


def test_the_offer_is_applied_as_the_remote_description():
    viewer = _viewer()
    viewer.process_offer("v=0 host-offer")
    [pc] = FakePeerConnection.instances
    [description] = pc.remote_descriptions
    assert (description.sdp, description.type) == ("v=0 host-offer", "offer")


def test_the_answer_uses_the_viewers_own_ice_servers():
    config = WebRTCConfig(ice_servers=["stun:example:3478"])
    _viewer(config=config).process_offer("v=0 host-offer")
    [pc] = FakePeerConnection.instances
    assert [s.urls for s in pc.configuration.iceServers] == [
        "stun:example:3478",
    ]


def test_a_second_offer_closes_the_first_peer_connection():
    viewer = _viewer()
    viewer.process_offer("v=0 host-offer")
    viewer.process_offer("v=0 host-offer-2")
    first, second = FakePeerConnection.instances
    assert first.closed
    assert not second.closed


def test_a_pinned_fingerprint_that_matches_lets_the_offer_through():
    sdp = "v=0\r\na=fingerprint:sha-256 AB:CD\r\n"
    assert _viewer().process_offer(sdp, "abcd") == "v=0 local-sdp"


def test_a_pinned_fingerprint_that_does_not_match_stops_the_handshake():
    # The point of pinning is catching a hijacked signaling slot while the
    # offer is still text -- so nothing may be built before the check.
    sdp = "v=0\r\na=fingerprint:sha-256 AB:CD\r\n"
    with pytest.raises(FingerprintMismatchError):
        _viewer().process_offer(sdp, "ffff")
    assert not FakePeerConnection.instances


def test_an_offer_with_no_fingerprint_at_all_is_refused_when_pinned():
    with pytest.raises(FingerprintMismatchError):
        _viewer().process_offer("v=0\r\nm=video 9 UDP/TLS/RTP/SAVPF\r\n", "ab")


# --- peer connection events ---------------------------------------------------

def test_the_state_callback_sees_every_transition():
    seen = []
    viewer = _viewer(on_state_change=seen.append)
    viewer.process_offer("v=0 host-offer")
    pc = FakePeerConnection.instances[0]
    for state in ("connecting", "connected", "closed"):
        pc.connectionState = state
        asyncio.run(pc.fire("connectionstatechange"))
    assert seen == ["connecting", "connected", "closed"]
    assert viewer.connection_state == "closed"


@pytest.mark.parametrize("state", ["failed", "closed", "disconnected"])
def test_a_lost_connection_drops_the_authenticated_flag(state):
    viewer = _viewer()
    viewer.process_offer("v=0 host-offer")
    viewer._authenticated = True
    pc = FakePeerConnection.instances[0]
    pc.connectionState = state
    asyncio.run(pc.fire("connectionstatechange"))
    assert viewer.authenticated is False


def test_a_raising_state_callback_does_not_break_the_handler():
    def _boom(_state):
        raise RuntimeError("Qt widget already deleted")

    viewer = _viewer(on_state_change=_boom)
    viewer.process_offer("v=0 host-offer")
    pc = FakePeerConnection.instances[0]
    pc.connectionState = "connected"
    asyncio.run(pc.fire("connectionstatechange"))


def test_an_inbound_video_track_starts_the_frame_pump():
    viewer = _viewer()
    viewer.process_offer("v=0 host-offer")

    async def _drive():
        FakePeerConnection.instances[0].fire("track", Track("video"))
        assert viewer._receive_task is not None
        viewer._receive_task.cancel()

    asyncio.run(_drive())


def test_an_inbound_audio_track_starts_host_voice_playback(monkeypatch):
    receivers = []

    class _Receiver:
        def __init__(self) -> None:
            self.consumed = []
            receivers.append(self)

        def consume(self, track):
            self.consumed.append(track)

    monkeypatch.setattr(
        "je_auto_control.utils.remote_desktop.webrtc_audio.OpusMicReceiver",
        _Receiver,
    )
    viewer = _viewer()
    viewer.process_offer("v=0 host-offer")
    track = Track("audio")
    FakePeerConnection.instances[0].fire("track", track)
    assert receivers[0].consumed == [track]


def test_a_second_audio_track_does_not_open_a_second_player(monkeypatch):
    class _Receiver:
        def consume(self, track):
            pass

    monkeypatch.setattr(
        "je_auto_control.utils.remote_desktop.webrtc_audio.OpusMicReceiver",
        _Receiver,
    )
    viewer = _viewer()
    viewer.process_offer("v=0 host-offer")
    pc = FakePeerConnection.instances[0]
    pc.fire("track", Track("audio"))
    first = viewer._host_voice_receiver
    pc.fire("track", Track("audio"))
    assert viewer._host_voice_receiver is first


def test_a_viewer_with_no_speaker_keeps_the_video(monkeypatch):
    def _no_device():
        raise OSError("no output device")

    monkeypatch.setattr(
        "je_auto_control.utils.remote_desktop.webrtc_audio.OpusMicReceiver",
        _no_device,
    )
    viewer = _viewer()
    viewer.process_offer("v=0 host-offer")
    FakePeerConnection.instances[0].fire("track", Track("audio"))
    assert viewer._host_voice_receiver is None


def test_a_track_that_is_neither_audio_nor_video_is_ignored():
    viewer = _viewer()
    viewer.process_offer("v=0 host-offer")
    FakePeerConnection.instances[0].fire("track", Track("application"))
    assert viewer._receive_task is None
    assert viewer._host_voice_receiver is None


def test_frames_reach_the_paint_callback():
    seen = []
    viewer = _viewer(on_frame=seen.append)
    asyncio.run(viewer._consume_video(FrameTrack("f1", "f2")))
    assert seen == ["f1", "f2"]


def test_the_end_of_the_stream_is_an_ending_not_an_escaping_exception():
    # `MediaStreamError` is how aiortc says "the host stopped sharing" -- the
    # ordinary way a session ends. It derives straight from Exception, so it
    # is not covered by the OSError / RuntimeError arm, and nobody awaits
    # this task: letting it out turns every clean disconnect into an
    # un-retrieved task exception. The host's drain loop always caught it;
    # this one did not until 2026-08-24.
    from aiortc.mediastreams import MediaStreamError
    viewer = _viewer(on_frame=lambda frame: None)
    asyncio.run(viewer._consume_video(
        FrameTrack("f1", ending=MediaStreamError()),
    ))


def test_a_transport_failure_also_ends_the_stream_quietly():
    viewer = _viewer(on_frame=lambda frame: None)
    asyncio.run(viewer._consume_video(FrameTrack(ending=OSError("reset"))))


def test_a_raising_paint_callback_does_not_end_the_stream():
    seen = []

    def _cb(frame):
        seen.append(frame)
        raise RuntimeError("QImage conversion failed")

    viewer = _viewer(on_frame=_cb)
    asyncio.run(viewer._consume_video(FrameTrack("f1", "f2")))
    assert seen == ["f1", "f2"]


def test_frames_with_no_listener_are_still_drained():
    track = FrameTrack("f1", "f2")
    asyncio.run(_viewer()._consume_video(track))
    assert track.frames == []


def test_the_frame_pump_stops_when_the_viewer_is_closing():
    viewer = _viewer(on_frame=lambda frame: None)
    viewer._closed.set()
    track = FrameTrack("f1")
    asyncio.run(viewer._consume_video(track))
    assert track.frames == ["f1"], "it never pulled a frame"


# --- data channel routing -----------------------------------------------------

@pytest.mark.parametrize("label,attribute", [
    ("mic", "_mic_channel"),
    ("files", "_files_channel"),
    ("usb", "_usb_channel"),
    ("ctrl", "_control_channel"),
])
def test_each_inbound_channel_is_routed_by_its_label(label, attribute):
    viewer = _viewer()
    viewer.process_offer("v=0 host-offer")
    channel = Channel(label)
    FakePeerConnection.instances[0].fire("datachannel", channel)
    assert getattr(viewer, attribute) is channel


def test_an_unknown_label_is_treated_as_the_control_channel():
    # The host names it "ctrl"; anything else arriving is still the channel
    # the auth handshake has to go out on, so it must not be dropped.
    viewer = _viewer()
    channel = Channel("control")
    viewer._attach_datachannel(channel)
    assert viewer._control_channel is channel


def test_the_control_channel_sends_auth_as_soon_as_it_opens():
    viewer = _viewer(viewer_id="viewer-3")
    channel = Channel("ctrl")
    viewer._attach_datachannel(channel)
    assert channel.sent == [], "not open yet"
    channel.fire("open")
    assert '"auth"' in channel.sent[0]
    assert '"viewer-3"' in channel.sent[0]


def test_a_channel_already_open_on_arrival_still_authenticates():
    # aiortc may fire "datachannel" after the channel is open, in which case
    # the "open" event never fires again and the handshake would never start.
    viewer = _viewer()
    viewer._attach_datachannel(Channel("ctrl", ready_state="open"))
    assert '"auth"' in viewer._control_channel.sent[0]


def test_the_usb_channel_gets_a_passthrough_client():
    viewer = _viewer()
    viewer._attach_datachannel(Channel("usb"))
    assert viewer.usb_client() is not None


def test_a_viewer_with_no_usb_channel_has_no_client():
    assert _viewer().usb_client() is None


# --- teardown -----------------------------------------------------------------

def test_stopping_a_viewer_that_never_connected_is_a_no_op(bridge):
    _viewer().stop()
    assert bridge.deferred == []


def test_stop_closes_the_connection_and_forgets_the_channels():
    viewer = _viewer()
    viewer.process_offer("v=0 host-offer")
    viewer._control_channel = Channel()
    viewer._files_channel = Channel("files")
    viewer._authenticated = True
    viewer.stop()
    assert FakePeerConnection.instances[0].closed
    assert viewer._pc is None
    assert viewer._control_channel is None
    assert viewer._files_channel is None
    assert viewer.authenticated is False


def test_stop_releases_every_stream_the_viewer_owns():
    viewer = _viewer()
    voice, opus, screen, mic = (Stoppable() for _ in range(4))
    viewer._host_voice_receiver = voice
    viewer._opus_audio_track = opus
    viewer._viewer_screen_track = screen
    viewer._mic_sender = mic
    asyncio.run(viewer._async_stop())
    assert all(s.stopped for s in (voice, opus, screen, mic))
    assert viewer._viewer_screen_track is None


def test_stop_cancels_the_frame_pump():
    viewer = _viewer()

    async def _drive():
        task = asyncio.ensure_future(asyncio.sleep(10))
        viewer._receive_task = task
        await viewer._async_stop()
        return task

    task = asyncio.run(_drive())
    assert task.cancelled()
    assert viewer._receive_task is None


def test_a_teardown_failure_does_not_abort_the_rest_of_the_teardown():
    viewer = _viewer()
    failing = Stoppable(error=OSError("device gone"))
    rest = Stoppable()
    viewer._host_voice_receiver = failing
    viewer._opus_audio_track = rest
    asyncio.run(viewer._async_stop())
    assert rest.stopped


def test_a_stop_that_times_out_is_reported_rather_than_raised(monkeypatch):
    monkeypatch.setattr(viewer_module, "get_bridge", HangingBridge)
    viewer = _viewer()
    viewer._pc = object()
    viewer.stop()


