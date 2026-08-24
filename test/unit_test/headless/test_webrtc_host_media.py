"""Turning the viewer's camera and microphone on and off, asymmetrically.

`MediaNegotiationMixin` exists because of one upstream fact its docstring
states: aiortc has no `removeTransceiver`. Enabling a viewer stream adds a
recvonly transceiver and re-offers; disabling can only mark the existing one
inactive and stop the receiver. The two directions therefore do different
things, and the slot each one reaches for is identified *by position* -- the
first video transceiver is the host's own outbound screen track, so the viewer's
is the second. Off-by-one there mutes the host's own screen share.

Nothing imported this module on any CI square before the `[webrtc]` extra joined
the measured install; it reaches `webrtc_transport`, which raises ImportError at
module level without aiortc.

`_pc`, the config and the spawn hook come from the host the mixin is mixed into,
and `_Host` supplies exactly the list the mixin's own docstring asks for.
"""
import asyncio

import pytest

from je_auto_control.utils.remote_desktop import webrtc_host_media as media
from je_auto_control.utils.remote_desktop.webrtc_host_media import (
    MediaNegotiationMixin,
)


class _Bridge:
    def call_soon(self, callback):
        callback()


class _Receiver:
    def __init__(self, track=None):
        self.track = track


class _Transceiver:
    def __init__(self, kind, track=None, direction="sendrecv"):
        self.kind = kind
        self.receiver = _Receiver(track) if track is not None else None
        self.direction = direction


class _PeerConnection:
    def __init__(self, *transceivers):
        self._transceivers = list(transceivers)
        self.added = []

    def getTransceivers(self):     # noqa: N802  # reason: the aiortc name
        return list(self._transceivers)

    def addTransceiver(self, kind, direction):   # noqa: N802  # the aiortc name
        self.added.append((kind, direction))
        self._transceivers.append(_Transceiver(kind, direction=direction))


class _Config:
    def __init__(self, *, accept_viewer_video=False,
                 accept_viewer_audio_opus=False):
        self.accept_viewer_video = accept_viewer_video
        self.accept_viewer_audio_opus = accept_viewer_audio_opus


class _Task:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class _Host(MediaNegotiationMixin):
    """A host with exactly the attributes the mixin's docstring asks for."""

    def __init__(self, pc=None, config=None):
        self._pc = pc
        self._config = config or _Config()
        self._viewer_video_task = None
        self._opus_audio_receiver = None
        self.sent = []
        self.spawned = []
        self.consumed = []
        self.opus_started = []

    def _send_ctrl(self, message):
        self.sent.append(message)

    def _spawn_bg(self, coroutine):
        if asyncio.iscoroutine(coroutine):
            coroutine.close()      # never awaited here; do not leak the frame
        self.spawned.append(coroutine)
        return coroutine

    def _consume_viewer_video(self, track):
        # The mixin calls this and hands the result to `_spawn_bg`, so the
        # double records at call time and returns something awaitable — a
        # coroutine body would not run until the task it never becomes.
        self.consumed.append(track)
        return self._noop()

    async def _noop(self):
        return None

    def _start_opus_audio_receive(self, track):
        self.opus_started.append(track)


@pytest.fixture(autouse=True)
def bridge(monkeypatch):
    monkeypatch.setattr(media, "get_bridge", _Bridge)


# === Nothing happens without a peer connection ==============================

@pytest.mark.parametrize("method", [
    "request_renegotiation", "enable_accept_viewer_video",
    "enable_accept_viewer_audio_opus", "disable_accept_viewer_video",
    "disable_accept_viewer_audio_opus",
])
def test_every_entry_point_is_inert_before_a_connection_exists(method):
    """These are GUI buttons; clicking one before connecting must not throw."""
    host = _Host(pc=None)
    getattr(host, method)()
    assert host.spawned == []
    assert host.sent == []


# === Enabling adds capacity =================================================

def test_enabling_viewer_video_adds_a_recvonly_slot_and_renegotiates():
    pc = _PeerConnection(_Transceiver("video"))       # the outbound screen
    host = _Host(pc, _Config())
    host.enable_accept_viewer_video()
    assert pc.added == [("video", "recvonly")]
    assert host._config.accept_viewer_video is True
    assert len(host.spawned) == 1                     # the renegotiation


def test_enabling_twice_does_not_add_a_second_slot():
    """Two recvonly video slots would be two SDP m-lines nothing fills."""
    pc = _PeerConnection(_Transceiver("video"))
    host = _Host(pc, _Config())
    host.enable_accept_viewer_video()
    host.enable_accept_viewer_video()
    assert pc.added == [("video", "recvonly")]
    assert len(host.spawned) == 2                     # but it re-offers again


def test_enabling_viewer_audio_adds_the_first_audio_slot():
    """There is no outbound audio slot to skip, so the first one is theirs."""
    pc = _PeerConnection(_Transceiver("video"))
    host = _Host(pc, _Config())
    host.enable_accept_viewer_audio_opus()
    assert pc.added == [("audio", "recvonly")]
    assert host._config.accept_viewer_audio_opus is True


def test_enabling_audio_twice_does_not_add_a_second_slot():
    pc = _PeerConnection(_Transceiver("video"))
    host = _Host(pc, _Config())
    host.enable_accept_viewer_audio_opus()
    host.enable_accept_viewer_audio_opus()
    assert pc.added == [("audio", "recvonly")]


# === Disabling can only deactivate ==========================================

def test_disabling_viewer_video_leaves_the_hosts_own_track_alone():
    """The first video transceiver is the screen share; muting it is the bug
    this test exists for."""
    outbound = _Transceiver("video")
    inbound = _Transceiver("video")
    host = _Host(_PeerConnection(outbound, inbound),
                 _Config(accept_viewer_video=True))
    host.disable_accept_viewer_video()
    assert inbound.direction == "inactive"
    assert outbound.direction == "sendrecv"
    assert host._config.accept_viewer_video is False


def test_disabling_viewer_video_cancels_the_consume_task():
    task = _Task()
    host = _Host(_PeerConnection(_Transceiver("video"), _Transceiver("video")),
                 _Config(accept_viewer_video=True))
    host._viewer_video_task = task
    host.disable_accept_viewer_video()
    assert task.cancelled is True
    assert host._viewer_video_task is None


def test_disabling_viewer_video_with_no_inbound_slot_still_renegotiates():
    host = _Host(_PeerConnection(_Transceiver("video")),
                 _Config(accept_viewer_video=True))
    host.disable_accept_viewer_video()
    assert len(host.spawned) == 1


def test_a_transceiver_that_refuses_to_go_inactive_does_not_stop_the_rest():
    class _Stubborn:
        kind = "video"
        receiver = None

        @property
        def direction(self):
            return "sendrecv"

        @direction.setter
        def direction(self, value):
            raise RuntimeError("closed")

    task = _Task()
    host = _Host(_PeerConnection(_Transceiver("video"), _Stubborn()),
                 _Config(accept_viewer_video=True))
    host._viewer_video_task = task
    host.disable_accept_viewer_video()
    assert task.cancelled is True
    assert len(host.spawned) == 1


def test_disabling_viewer_audio_deactivates_and_stops_the_receiver():
    class _Opus:
        stopped = False

        def stop(self):
            self.stopped = True

    audio = _Transceiver("audio")
    receiver = _Opus()
    host = _Host(_PeerConnection(_Transceiver("video"), audio),
                 _Config(accept_viewer_audio_opus=True))
    host._opus_audio_receiver = receiver
    host.disable_accept_viewer_audio_opus()
    assert audio.direction == "inactive"
    assert receiver.stopped is True
    assert host._opus_audio_receiver is None


def test_a_receiver_that_throws_on_stop_is_still_dropped():
    class _Opus:
        def stop(self):
            raise OSError("already gone")

    host = _Host(_PeerConnection(_Transceiver("audio")),
                 _Config(accept_viewer_audio_opus=True))
    host._opus_audio_receiver = _Opus()
    host.disable_accept_viewer_audio_opus()
    assert host._opus_audio_receiver is None


# === Re-subscribing after a renegotiation ===================================

def test_the_viewer_video_track_is_picked_up_from_the_second_slot():
    track = object()
    pc = _PeerConnection(_Transceiver("video", track=object()),
                         _Transceiver("video", track=track))
    host = _Host(pc, _Config(accept_viewer_video=True))
    host._maybe_resubscribe_viewer_video()
    assert host.consumed == [track]
    assert host._viewer_video_task is not None


def test_no_resubscribe_when_the_feature_is_off():
    pc = _PeerConnection(_Transceiver("video"), _Transceiver("video",
                                                             track=object()))
    host = _Host(pc, _Config(accept_viewer_video=False))
    host._maybe_resubscribe_viewer_video()
    assert host.consumed == []


def test_no_resubscribe_when_a_task_is_already_running():
    pc = _PeerConnection(_Transceiver("video"), _Transceiver("video",
                                                             track=object()))
    host = _Host(pc, _Config(accept_viewer_video=True))
    host._viewer_video_task = _Task()
    host._maybe_resubscribe_viewer_video()
    assert host.consumed == []


def test_a_slot_with_no_track_yet_is_skipped():
    """A transceiver exists as soon as it is negotiated; the track arrives
    later."""
    pc = _PeerConnection(_Transceiver("video"), _Transceiver("video"))
    host = _Host(pc, _Config(accept_viewer_video=True))
    host._maybe_resubscribe_viewer_video()
    assert host.consumed == []
    assert host._viewer_video_task is None


def test_the_viewer_audio_track_is_picked_up_from_any_audio_slot():
    track = object()
    pc = _PeerConnection(_Transceiver("video", track=object()),
                         _Transceiver("audio", track=track))
    host = _Host(pc, _Config(accept_viewer_audio_opus=True))
    host._maybe_resubscribe_viewer_audio()
    assert host.opus_started == [track]


def test_no_audio_resubscribe_when_a_receiver_is_already_running():
    pc = _PeerConnection(_Transceiver("audio", track=object()))
    host = _Host(pc, _Config(accept_viewer_audio_opus=True))
    host._opus_audio_receiver = object()
    host._maybe_resubscribe_viewer_audio()
    assert host.opus_started == []


# === The host-initiated offer ===============================================

def test_renegotiation_sends_the_new_offer_over_the_control_channel(
        monkeypatch):
    class _Description:
        sdp = "v=0\r\nfake offer\r\n"

    class _Negotiating(_PeerConnection):
        localDescription = _Description()

        async def createOffer(self):     # noqa: N802  # reason: the aiortc name
            return _Description()

        async def setLocalDescription(self, offer):   # noqa: N802
            self.local = offer

    async def _gathered(pc):
        return None

    monkeypatch.setattr(media, "wait_for_ice_gathering", _gathered)
    host = _Host(_Negotiating(), _Config())
    asyncio.run(host._async_renegotiate())
    assert host.sent == [{"type": "renegotiate_offer",
                          "sdp": "v=0\r\nfake offer\r\n"}]


def test_a_failed_offer_sends_nothing_rather_than_a_half_negotiation(
        monkeypatch):
    class _Broken(_PeerConnection):
        async def createOffer(self):     # noqa: N802  # reason: the aiortc name
            raise RuntimeError("connection closed")

    host = _Host(_Broken(), _Config())
    asyncio.run(host._async_renegotiate())
    assert host.sent == []


def test_renegotiating_without_a_connection_is_a_no_op():
    host = _Host(pc=None)
    asyncio.run(host._async_renegotiate())
    assert host.sent == []
