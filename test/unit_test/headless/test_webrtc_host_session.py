"""Building, renegotiating and tearing down a host session.

`WebRTCDesktopHost` is the largest thing under `utils/remote_desktop` and,
until the `[webrtc]` extra joined the measured install, one of the least
covered: it reaches `webrtc_transport`, which raises ImportError at module
level without aiortc. Its two mixins already have tests
(`test_webrtc_host_auth.py`, `test_webrtc_host_media.py`); this file covers
the class those are mixed into.

It splits along the seam the class itself has. Here: the session -- offer
construction, answer application, the connection-state handlers, and
teardown. The DataChannel traffic that rides on top is in
`test_webrtc_host_channels.py`.

`RTCPeerConnection` and `ScreenVideoTrack` are replaced, from
`headless._webrtc_doubles`. A real one of either would open a screen
grabber and start STUN traffic on a CI runner,
and neither is what these tests are about: what matters is the *shape* of
the offer the host builds -- which transceivers it adds for which config,
which four DataChannels it opens, and in what order -- because that shape
is what the viewer's `_attach_viewer_screen_track` counts m-lines in.

Teardown gets the same attention as setup for one reason: the host does
not own everything it holds. A relayed track belongs to `MultiViewerHost`,
and stopping it there would blank the screen for every *other* viewer.
"""
from __future__ import annotations

import asyncio

import pytest

from headless._webrtc_doubles import (
    AuditLog, Bridge, FakePeerConnection, FrameTrack, HangingBridge,
    Stoppable, Track, noop_ice_gathering,
)
from je_auto_control.utils.remote_desktop import webrtc_host as host_module
from je_auto_control.utils.remote_desktop.permissions import SessionPermissions
from je_auto_control.utils.remote_desktop.webrtc_host import WebRTCDesktopHost
from je_auto_control.utils.remote_desktop.webrtc_transport import WebRTCConfig


@pytest.fixture
def bridge(monkeypatch):
    fake = Bridge()
    monkeypatch.setattr(host_module, "get_bridge", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def fake_peer_connection(monkeypatch):
    """Replace the two collaborators that would touch a screen or a socket."""
    FakePeerConnection.instances = []
    monkeypatch.setattr(host_module, "RTCPeerConnection", FakePeerConnection)
    monkeypatch.setattr(host_module, "ScreenVideoTrack",
                        lambda **kwargs: Track("video"))
    monkeypatch.setattr(host_module, "wait_for_ice_gathering",
                        noop_ice_gathering)
    yield
    FakePeerConnection.instances = []


@pytest.fixture(autouse=True)
def fake_audit_log(monkeypatch):
    log = AuditLog()
    monkeypatch.setattr(host_module, "default_audit_log", lambda: log)
    return log


def _host(**kwargs) -> WebRTCDesktopHost:
    kwargs.setdefault("token", "secret")
    return WebRTCDesktopHost(**kwargs)


# --- construction -------------------------------------------------------------

def test_a_host_without_a_token_is_refused():
    with pytest.raises(ValueError, match="non-empty token"):
        WebRTCDesktopHost(token="")


def test_read_only_shorthand_becomes_a_permission_set():
    assert _host(read_only=True).read_only is True
    assert _host(read_only=True).permissions.allow_files is False
    assert _host().read_only is False


def test_explicit_permissions_win_over_the_shorthand():
    permissions = SessionPermissions.view_only()
    assert _host(read_only=False, permissions=permissions).permissions is (
        permissions
    )


def test_a_fresh_host_is_neither_authenticated_nor_connected():
    host = _host()
    assert host.authenticated is False
    assert host.connection_state == "closed", "no PeerConnection yet"


# --- building the offer -------------------------------------------------------

def test_create_offer_returns_the_local_sdp(bridge):
    host = _host()
    assert host.create_offer() == "v=0 local-sdp"
    assert host.connection_state == "new"


def test_create_offer_asks_the_consent_callback_first(bridge):
    seen = []

    def _consent(peer_label):
        seen.append(peer_label)
        return True

    _host(offer_consent=_consent).create_offer(peer_label="Ops laptop")
    assert seen == ["Ops laptop"]


def test_a_rejected_offer_never_builds_a_peer_connection(bridge):
    host = _host(offer_consent=lambda peer: False)
    with pytest.raises(PermissionError, match="rejected by consent"):
        host.create_offer()
    assert not FakePeerConnection.instances, "no capture, no ICE, nothing started"


def test_the_offer_carries_the_configured_ice_servers(bridge):
    config = WebRTCConfig(ice_servers=["stun:example:3478"])
    _host(config=config).create_offer()
    [pc] = FakePeerConnection.instances
    assert [s.urls for s in pc.configuration.iceServers] == [
        "stun:example:3478",
    ]


def test_the_offer_opens_the_four_data_channels_the_viewer_expects(bridge):
    _host().create_offer()
    [pc] = FakePeerConnection.instances
    assert [c.label for c in pc.channels] == ["ctrl", "mic", "files", "usb"]


def test_the_screen_track_is_the_first_media_line(bridge):
    # The viewer identifies the slot for its own screen by m-line order, so
    # the host's outbound track has to be added before any recvonly slot.
    config = WebRTCConfig(accept_viewer_video=True)
    _host(config=config).create_offer()
    [pc] = FakePeerConnection.instances
    assert len(pc.tracks) == 1
    assert pc.transceivers == [("video", "recvonly")]


def test_no_inbound_slots_are_advertised_by_default(bridge):
    _host().create_offer()
    assert FakePeerConnection.instances[0].transceivers == []


def test_accepting_viewer_audio_advertises_a_recvonly_audio_slot(bridge):
    config = WebRTCConfig(accept_viewer_audio_opus=True)
    _host(config=config).create_offer()
    assert FakePeerConnection.instances[0].transceivers == [("audio", "recvonly")]


def test_an_external_track_is_used_as_is(bridge):
    # `MultiViewerHost` hands each session a relay proxy of one shared
    # capture; building a second grabber here would be a second screen read
    # per viewer.
    relayed = Track("video")
    _host(external_video_track=relayed).create_offer()
    assert FakePeerConnection.instances[0].tracks == [relayed]


def test_host_voice_attaches_a_microphone_track(bridge, monkeypatch):
    mic = Track("audio")
    monkeypatch.setattr(
        "je_auto_control.utils.remote_desktop.webrtc_audio.OpusMicAudioTrack",
        lambda: mic,
    )
    _host(config=WebRTCConfig(host_voice=True)).create_offer()
    assert mic in FakePeerConnection.instances[0].tracks


def test_a_host_with_no_microphone_still_gets_an_offer(bridge, monkeypatch):
    # No input device is the normal state of a server; the screen share must
    # not be lost because the mic could not be opened.
    def _no_device():
        raise OSError("no input device")

    monkeypatch.setattr(
        "je_auto_control.utils.remote_desktop.webrtc_audio.OpusMicAudioTrack",
        _no_device,
    )
    host = _host(config=WebRTCConfig(host_voice=True))
    assert host.create_offer() == "v=0 local-sdp"
    assert host._host_voice_track is None


def test_a_second_offer_closes_the_first_peer_connection(bridge):
    host = _host()
    host.create_offer()
    host.create_offer()
    first, second = FakePeerConnection.instances
    assert first.closed
    assert not second.closed


# --- applying the answer ------------------------------------------------------

@pytest.mark.parametrize("answer", ["", "   "])
def test_an_empty_answer_is_refused_before_it_reaches_aiortc(bridge, answer):
    host = _host()
    host.create_offer()
    with pytest.raises(ValueError, match="answer_sdp is empty"):
        host.accept_answer(answer)


def test_accept_answer_before_create_offer_is_a_runtime_error(bridge):
    with pytest.raises(RuntimeError, match="create_offer"):
        _host().accept_answer("v=0 answer")


def test_accept_answer_applies_it_and_arms_the_auth_deadline(bridge):
    host = _host()
    host.create_offer()
    host.accept_answer("v=0 answer")
    [pc] = FakePeerConnection.instances
    [description] = pc.remote_descriptions
    assert (description.sdp, description.type) == ("v=0 answer", "answer")
    assert host._auth_deadline_handle is not None, "the grace period is armed"


# --- connection state ---------------------------------------------------------

def test_the_state_callback_sees_every_transition(bridge):
    seen = []
    host = _host(on_state_change=seen.append)
    host.create_offer()
    pc = FakePeerConnection.instances[0]
    for state in ("connecting", "connected", "failed"):
        pc.connectionState = state
        asyncio.run(pc.fire("connectionstatechange"))
    assert seen == ["connecting", "connected", "failed"]


@pytest.mark.parametrize("state", ["failed", "closed", "disconnected"])
def test_a_lost_connection_drops_the_authenticated_flag(bridge, state):
    # Anything that reconnects starts a new session and must authenticate
    # again; leaving the flag set would let a reused channel skip the token.
    host = _host()
    host.create_offer()
    host._authenticated = True
    pc = FakePeerConnection.instances[0]
    pc.connectionState = state
    asyncio.run(pc.fire("connectionstatechange"))
    assert host.authenticated is False


def test_a_raising_state_callback_does_not_break_the_handler(bridge):
    def _boom(_state):
        raise RuntimeError("Qt widget already deleted")

    host = _host(on_state_change=_boom)
    host.create_offer()
    pc = FakePeerConnection.instances[0]
    pc.connectionState = "connected"
    asyncio.run(pc.fire("connectionstatechange"))


def test_connecting_snapshots_the_remote_ip_from_the_selected_pair(bridge):
    host = _host()
    host.create_offer()
    pc = FakePeerConnection.instances[0]
    pc.stats = _stats_with_selected_pair(ip="203.0.113.9")
    pc.connectionState = "connected"
    asyncio.run(pc.fire("connectionstatechange"))
    assert host._remote_ip == "203.0.113.9"


def _stat(**fields):
    return type("_Stat", (), fields)()


def _stats_with_selected_pair(*, ip=None, address=None, remote_id="remote-1",
                              include_remote=True):
    stats = {"pair-1": _stat(type="candidate-pair", selected=True,
                             remoteCandidateId=remote_id)}
    if include_remote:
        fields = {}
        if ip is not None:
            fields["ip"] = ip
        if address is not None:
            fields["address"] = address
        stats[remote_id] = _stat(**fields)
    return stats


def test_the_remote_ip_falls_back_to_the_address_field():
    # aiortc renamed `ip` to `address` following the spec; both spellings
    # turn up depending on the version installed.
    report = _stats_with_selected_pair(address="198.51.100.4")
    assert WebRTCDesktopHost._extract_remote_ip(report) == "198.51.100.4"


def test_an_unselected_candidate_pair_is_not_the_remote_peer():
    report = {"pair-1": _stat(type="candidate-pair", selected=False,
                              remoteCandidateId="remote-1")}
    assert WebRTCDesktopHost._extract_remote_ip(report) is None


def test_a_dangling_candidate_reference_yields_no_ip():
    report = _stats_with_selected_pair(include_remote=False)
    assert WebRTCDesktopHost._extract_remote_ip(report) is None


def test_a_candidate_with_neither_ip_nor_address_yields_no_ip():
    report = _stats_with_selected_pair()
    assert WebRTCDesktopHost._extract_remote_ip(report) is None


def test_stats_that_cannot_be_read_leave_the_ip_unknown(bridge):
    # The IP feeds the whitelist check and the audit log; failing to read it
    # must not fail the connection.
    host = _host()
    host.create_offer()
    FakePeerConnection.instances[0].stats_error = RuntimeError("pc already closed")
    asyncio.run(host._snapshot_remote_ip())
    assert host._remote_ip is None


def test_snapshotting_without_a_peer_connection_is_a_no_op():
    asyncio.run(_host()._snapshot_remote_ip())


# --- inbound viewer media -----------------------------------------------------

def test_an_inbound_video_track_starts_a_consume_task(bridge):
    host = _host()
    host.create_offer()

    async def _drive():
        FakePeerConnection.instances[0].fire("track", Track("video"))
        assert host._viewer_video_task is not None
        host._viewer_video_task.cancel()

    asyncio.run(_drive())


def test_an_inbound_audio_track_is_ignored_unless_it_was_advertised(bridge):
    host = _host()
    host.create_offer()
    FakePeerConnection.instances[0].fire("track", Track("audio"))
    assert host._opus_audio_receiver is None


def test_an_advertised_audio_track_starts_an_opus_receiver(bridge,
                                                           monkeypatch):
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
    host = _host(config=WebRTCConfig(accept_viewer_audio_opus=True))
    host.create_offer()
    track = Track("audio")
    FakePeerConnection.instances[0].fire("track", track)
    assert receivers[0].consumed == [track]


def test_a_second_audio_track_does_not_open_a_second_receiver(bridge,
                                                              monkeypatch):
    class _Receiver:
        def __init__(self) -> None:
            self.consumed = []

        def consume(self, track):
            self.consumed.append(track)

    monkeypatch.setattr(
        "je_auto_control.utils.remote_desktop.webrtc_audio.OpusMicReceiver",
        _Receiver,
    )
    host = _host(config=WebRTCConfig(accept_viewer_audio_opus=True))
    host.create_offer()
    pc = FakePeerConnection.instances[0]
    pc.fire("track", Track("audio"))
    first = host._opus_audio_receiver
    pc.fire("track", Track("audio"))
    assert host._opus_audio_receiver is first


def test_a_missing_speaker_does_not_break_the_session(bridge, monkeypatch):
    def _no_device():
        raise OSError("no output device")

    monkeypatch.setattr(
        "je_auto_control.utils.remote_desktop.webrtc_audio.OpusMicReceiver",
        _no_device,
    )
    host = _host(config=WebRTCConfig(accept_viewer_audio_opus=True))
    host.create_offer()
    FakePeerConnection.instances[0].fire("track", Track("audio"))
    assert host._opus_audio_receiver is None


def test_viewer_frames_are_dropped_until_the_viewer_authenticates():
    # The video slot opens with the PeerConnection, which is before the
    # token has been checked: frames arriving in that window are a stream
    # from a peer we have not accepted yet.
    host = _host()
    seen = []
    host.set_viewer_video_callback(seen.append)
    asyncio.run(host._consume_viewer_video(FrameTrack("f1", "f2")))
    assert seen == []


def test_viewer_frames_reach_the_callback_once_authenticated():
    host = _host()
    seen = []
    host.set_viewer_video_callback(seen.append)
    host._authenticated = True
    asyncio.run(host._consume_viewer_video(FrameTrack("f1", "f2")))
    assert seen == ["f1", "f2"]


def test_viewer_frames_with_no_listener_are_drained_and_discarded():
    # Nothing is registered until the GUI opens the viewer-screen window;
    # the frames still have to be pulled or the receiver backs up.
    host = _host()
    host._authenticated = True
    track = FrameTrack("f1", "f2")
    asyncio.run(host._consume_viewer_video(track))
    assert track.frames == []


def test_a_track_that_is_neither_audio_nor_video_is_ignored(bridge):
    host = _host()
    host.create_offer()
    FakePeerConnection.instances[0].fire("track", Track("application"))
    assert host._viewer_video_task is None
    assert host._opus_audio_receiver is None


def test_a_raising_frame_callback_does_not_end_the_stream():
    host = _host()
    host._authenticated = True
    seen = []

    def _cb(frame):
        seen.append(frame)
        raise RuntimeError("paint failed")

    host.set_viewer_video_callback(_cb)
    asyncio.run(host._consume_viewer_video(FrameTrack("f1", "f2")))
    assert seen == ["f1", "f2"], "the second frame was still delivered"


def test_the_consume_task_clears_itself_when_the_stream_ends():
    host = _host()
    host._viewer_video_task = "placeholder"
    asyncio.run(host._consume_viewer_video(FrameTrack(ending=OSError("gone"))))
    assert host._viewer_video_task is None


# --- teardown -----------------------------------------------------------------

def test_stopping_a_host_that_never_connected_is_a_no_op(bridge):
    _host().stop()
    assert not bridge.deferred


def test_stop_closes_the_peer_connection_and_forgets_the_channels(bridge):
    host = _host()
    host.create_offer()
    host._authenticated = True
    host.stop()
    assert FakePeerConnection.instances[0].closed
    assert host._pc is None
    assert host._control_channel is None
    assert host._files_channel is None
    assert host.authenticated is False
    assert host.connection_state == "closed"


def test_stop_stops_a_capture_the_host_created():
    host = _host()
    track = Track("video")
    host._video_track = track
    asyncio.run(host._async_stop())
    assert track.stopped


def test_stop_leaves_a_relayed_track_alone():
    # `MultiViewerHost` owns the shared capture; stopping it from one
    # session would blank the screen for every other viewer.
    relayed = Track("video")
    host = _host(external_video_track=relayed)
    host._video_track = relayed
    asyncio.run(host._async_stop())
    assert not relayed.stopped


def test_stop_releases_the_audio_and_mic_helpers():
    host = _host()
    voice, receiver, mic = Stoppable(), Stoppable(), Stoppable()
    host._host_voice_track = voice
    host._opus_audio_receiver = receiver
    host._mic_receiver = mic
    asyncio.run(host._async_stop())
    assert (voice.stopped, receiver.stopped, mic.stopped) == (True, True, True)
    assert host._host_voice_track is None
    assert host._opus_audio_receiver is None
    assert host._mic_receiver is None


def test_stop_cancels_the_viewer_video_task_and_the_auth_deadline():
    host = _host()

    async def _drive():
        task = asyncio.ensure_future(asyncio.sleep(10))
        handle = asyncio.get_event_loop().call_later(10, lambda: None)
        host._viewer_video_task = task
        host._auth_deadline_handle = handle
        await host._async_stop()
        return task, handle

    task, handle = asyncio.run(_drive())
    assert task.cancelled()
    assert handle.cancelled()
    assert host._auth_deadline_handle is None


def test_a_teardown_failure_does_not_abort_the_rest_of_the_teardown():
    host = _host()
    voice = Stoppable(error=OSError("device gone"))
    receiver = Stoppable()
    host._host_voice_track = voice
    host._opus_audio_receiver = receiver
    asyncio.run(host._async_stop())
    assert receiver.stopped, "teardown continued past the failure"


def test_stop_quietly_ignores_a_collaborator_that_was_never_built():
    WebRTCDesktopHost._stop_quietly(None, "nothing")


def test_a_stop_that_times_out_is_reported_rather_than_raised(monkeypatch):
    monkeypatch.setattr(host_module, "get_bridge", HangingBridge)
    host = _host()
    host._pc = object()
    host.stop()   # the GUI's close button must not raise
