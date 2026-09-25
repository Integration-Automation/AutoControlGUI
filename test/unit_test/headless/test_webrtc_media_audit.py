"""WebRTC media and audio-device defects from the 2026-09-24 audit (fakes only; no devices, no screen).

A PortAudioError escaped every guard and a stream that failed to start was
kept; a block with a status flag was dropped; the screen track stamped every
frame 1/30 s apart whatever its rate; a Zeroconf whose registration failed
was left running; the asyncio bridge could not stop a loop with work pending.
"""
import asyncio
import types

import pytest

pytest.importorskip("aiortc")

from je_auto_control.utils.exception.exceptions import AutoControlException  # noqa: E402
from je_auto_control.utils.remote_desktop import audio as audio_mod  # noqa: E402
from je_auto_control.utils.remote_desktop.audio import (  # noqa: E402
    AudioBackendError, AudioCapture, AudioPlayer,
)


class _PortAudioError(Exception):
    """sounddevice's error type, which derives from ``Exception`` directly."""


class _Stream:
    def __init__(self, fail_start=False, fail_write=False, callback=None):
        self.fail_start, self.fail_write = fail_start, fail_write
        self.callback = callback
        self.closed = False

    def start(self):
        if self.fail_start:
            raise _PortAudioError("Error querying device -1")

    def write(self, _data):
        if self.fail_write:
            raise _PortAudioError("device removed")

    def stop(self):
        pass

    def close(self):
        self.closed = True


def _fake_sd(monkeypatch, **stream_options):
    streams = []

    def make(**kwargs):
        stream = _Stream(callback=kwargs.get("callback"), **stream_options)
        streams.append(stream)
        return stream

    fake = types.SimpleNamespace(PortAudioError=_PortAudioError,
                                 RawInputStream=make, RawOutputStream=make)
    monkeypatch.setattr(audio_mod, "_load_sounddevice", lambda: fake)
    return streams


def test_a_device_that_fails_to_start_is_closed_and_reported(monkeypatch):
    streams = _fake_sd(monkeypatch, fail_start=True)
    player = AudioPlayer()
    with pytest.raises(AudioBackendError):
        player.start()
    assert streams[0].closed and not player.is_running
    assert issubclass(AudioBackendError, AutoControlException)


def test_a_late_write_error_is_dropped(monkeypatch):
    _fake_sd(monkeypatch, fail_write=True)
    player = AudioPlayer()
    player.start()
    player.play(b"\0\0")


def test_a_block_with_a_status_flag_is_still_delivered(monkeypatch):
    streams = _fake_sd(monkeypatch)
    blocks = []
    capture = AudioCapture(on_block=blocks.append)
    capture.start()
    streams[0].callback(b"\1\2", 1, None, "input overflow")
    assert blocks == [b"\1\2"]


def test_the_screen_track_stamps_frames_at_the_real_rate(monkeypatch):
    from je_auto_control.utils.remote_desktop import webrtc_transport
    clock = [100.0]
    monkeypatch.setattr(webrtc_transport.time, "monotonic", lambda: clock[0])
    track = webrtc_transport.ScreenVideoTrack(fps=10)
    first, time_base = track._timestamp()
    clock[0] += 0.1
    second, _ = track._timestamp()
    assert (second - first) * time_base == pytest.approx(0.1)


def test_a_failed_registration_closes_zeroconf(monkeypatch):
    from je_auto_control.utils.remote_desktop import lan_discovery
    closed = []

    class _Zeroconf:
        def register_service(self, _info):
            raise RuntimeError("NonUniqueNameException")

        def close(self):
            closed.append(True)

    monkeypatch.setattr(lan_discovery, "_AVAILABLE", True)
    monkeypatch.setattr(lan_discovery, "Zeroconf", _Zeroconf, raising=False)
    monkeypatch.setattr(lan_discovery, "ServiceInfo", lambda *a, **k: object(), raising=False)
    with pytest.raises(RuntimeError):
        lan_discovery.HostAdvertiser(host_id="h1")
    assert closed == [True]


def test_the_bridge_stops_with_work_pending():
    from je_auto_control.utils.remote_desktop.webrtc_transport import _AsyncioBridge
    bridge = _AsyncioBridge()
    loop = bridge.start()
    future = bridge.submit(asyncio.sleep(3600))
    bridge.stop()
    assert future.cancelled() and loop.is_closed()
