"""The arithmetic that decides the remote-desktop link is going bad.

`StatsPoller` turns aiortc's cumulative `getStats()` counters into the per-sample
rates `AdaptiveBitrateController` acts on: bitrate, fps, packet loss, RTT and
jitter. Every one of those is a *delta* between two samples, which is where this
kind of code goes wrong -- a first sample with no predecessor, a counter that
resets when a track is replaced, a report that names no candidate pair. Get one
wrong and the controller drops the frame rate on a link that is fine, or holds a
high rate on one that is not.

Nothing imported this module on any CI square before the `[webrtc]` extra joined
the measured install: it is reachable only through `webrtc_transport`, which
raises ImportError at module level without aiortc.

The poller is driven here through `_sample()` on a bare event loop rather than
through `start()`, because `start()` submits to the shared asyncio bridge and
what is under test is the arithmetic, not the bridge.
"""
import asyncio

import pytest

from je_auto_control.utils.remote_desktop import webrtc_stats
from je_auto_control.utils.remote_desktop.webrtc_stats import (
    StatsPoller, StatsSnapshot,
)


class _Entry:
    """One `RTCStats` row: aiortc exposes these as attributes."""

    def __init__(self, **fields):
        self.__dict__.update(fields)


class _PeerConnection:
    """Hands back one prepared report per `getStats()` call."""

    def __init__(self, *reports):
        self._reports = list(reports)
        self.calls = 0

    async def getStats(self):          # noqa: N802  # reason: the aiortc name
        self.calls += 1
        report = self._reports.pop(0) if self._reports else {}
        return {str(index): entry for index, entry in enumerate(report)}


def _inbound(**fields):
    return _Entry(type="inbound-rtp", kind="video", **fields)


class _Clock:
    """A monotonic clock the test drives.

    Replaces the module's own ``time`` binding rather than ``time.monotonic``
    itself: asyncio reads the real clock while these coroutines run, and a
    fake installed globally makes the event loop read the fake too.
    """

    def __init__(self, *ticks):
        self._ticks = list(ticks)

    def monotonic(self):
        return self._ticks.pop(0) if len(self._ticks) > 1 else self._ticks[0]


def _pin_clock(monkeypatch, *ticks):
    monkeypatch.setattr(webrtc_stats, "time", _Clock(*ticks))


def _sample(poller):
    """Take one sample."""
    return asyncio.run(poller._sample())


# === A poller with nothing to poll ==========================================

def test_a_poller_without_a_peer_connection_samples_nothing():
    assert asyncio.run(StatsPoller(None, lambda snap: None)._sample()) is None


def test_an_empty_report_yields_an_empty_snapshot():
    poller = StatsPoller(_PeerConnection([]), lambda snap: None)
    snapshot = _sample(poller)
    assert snapshot.to_dict() == StatsSnapshot().to_dict()


def test_the_poll_interval_has_a_floor():
    """A caller asking for a 1 ms poll would spin the loop, not measure it."""
    assert StatsPoller(None, lambda snap: None, interval_s=0.001)._interval == 0.25
    assert StatsPoller(None, lambda snap: None, interval_s=5)._interval == 5.0


# === Rates need two samples =================================================

def test_the_first_sample_reports_no_rate():
    """There is nothing to subtract from yet; a rate would be invented."""
    poller = StatsPoller(
        _PeerConnection([_inbound(bytesReceived=10_000, framesDecoded=30)]),
        lambda snap: None)
    snapshot = _sample(poller)
    assert snapshot.bitrate_kbps is None
    assert snapshot.fps is None


def test_the_second_sample_reports_the_rate_between_them(monkeypatch):
    reports = [[_inbound(bytesReceived=0, framesDecoded=0)],
               [_inbound(bytesReceived=125_000, framesDecoded=60)]]
    poller = StatsPoller(_PeerConnection(*reports), lambda snap: None)
    _pin_clock(monkeypatch, 100.0, 102.0)
    _sample(poller)
    snapshot = _sample(poller)
    # 125,000 bytes over 2 s = 500 kbit/s; 60 frames over 2 s = 30 fps.
    assert snapshot.bitrate_kbps == pytest.approx(500.0)
    assert snapshot.fps == pytest.approx(30.0)


def test_a_counter_that_went_backwards_reports_no_rate(monkeypatch):
    """A replaced track restarts the counters; a negative delta is not a rate."""
    reports = [[_inbound(bytesReceived=125_000, framesDecoded=60)],
               [_inbound(bytesReceived=10, framesDecoded=1)]]
    poller = StatsPoller(_PeerConnection(*reports), lambda snap: None)
    _pin_clock(monkeypatch, 100.0, 102.0)
    _sample(poller)
    snapshot = _sample(poller)
    assert snapshot.bitrate_kbps is None
    assert snapshot.fps is None


def test_two_samples_at_the_same_instant_report_no_rate(monkeypatch):
    """Dividing by a zero interval is the other way to invent a number."""
    reports = [[_inbound(bytesReceived=0)], [_inbound(bytesReceived=125_000)]]
    poller = StatsPoller(_PeerConnection(*reports), lambda snap: None)
    _pin_clock(monkeypatch, 100.0)
    _sample(poller)
    assert _sample(poller).bitrate_kbps is None


# === Packet loss is measured over the interval, not since the connection ====

def test_loss_is_the_recent_ratio_not_the_lifetime_one(monkeypatch):
    """A link that lost 50 packets an hour ago is not a link losing them now."""
    reports = [[_inbound(packetsReceived=1_000, packetsLost=50)],
               [_inbound(packetsReceived=1_100, packetsLost=50)]]
    poller = StatsPoller(_PeerConnection(*reports), lambda snap: None)
    _pin_clock(monkeypatch, 100.0, 101.0)
    _sample(poller)
    assert _sample(poller).packet_loss_pct == pytest.approx(0.0)


def test_loss_in_the_last_interval_is_reported(monkeypatch):
    reports = [[_inbound(packetsReceived=1_000, packetsLost=0)],
               [_inbound(packetsReceived=1_090, packetsLost=10)]]
    poller = StatsPoller(_PeerConnection(*reports), lambda snap: None)
    _pin_clock(monkeypatch, 100.0, 101.0)
    _sample(poller)
    # 10 lost out of 100 sent in the interval.
    assert _sample(poller).packet_loss_pct == pytest.approx(10.0)


def test_a_report_with_no_packets_at_all_reports_no_loss():
    poller = StatsPoller(
        _PeerConnection([_inbound(packetsReceived=0, packetsLost=0)]),
        lambda snap: None)
    assert _sample(poller).packet_loss_pct is None


def test_missing_counters_read_as_zero_rather_than_raising():
    """aiortc omits attributes it has no value for."""
    poller = StatsPoller(_PeerConnection([_inbound()]), lambda snap: None)
    assert _sample(poller).packet_loss_pct is None


def test_a_null_counter_reads_as_zero():
    poller = StatsPoller(
        _PeerConnection([_inbound(packetsReceived=None, packetsLost=None)]),
        lambda snap: None)
    assert _sample(poller).packet_loss_pct is None


# === Where RTT and jitter come from =========================================

def test_the_remote_report_supplies_rtt_and_jitter_in_milliseconds():
    entry = _Entry(type="remote-inbound-rtp", roundTripTime=0.125, jitter=0.004)
    poller = StatsPoller(_PeerConnection([entry]), lambda snap: None)
    snapshot = _sample(poller)
    assert snapshot.rtt_ms == pytest.approx(125.0)
    assert snapshot.jitter_ms == pytest.approx(4.0)


def test_the_candidate_pair_supplies_rtt_when_the_remote_report_does_not():
    entry = _Entry(type="candidate-pair", currentRoundTripTime=0.05)
    poller = StatsPoller(_PeerConnection([entry]), lambda snap: None)
    assert _sample(poller).rtt_ms == pytest.approx(50.0)


def test_the_remote_report_wins_over_the_candidate_pair():
    """Both are in the report; the one measured end to end is the real one."""
    report = [_Entry(type="remote-inbound-rtp", roundTripTime=0.125),
              _Entry(type="candidate-pair", currentRoundTripTime=0.05)]
    poller = StatsPoller(_PeerConnection(report), lambda snap: None)
    assert _sample(poller).rtt_ms == pytest.approx(125.0)


def test_a_candidate_pair_with_no_measurement_is_ignored():
    entry = _Entry(type="candidate-pair", currentRoundTripTime=None)
    poller = StatsPoller(_PeerConnection([entry]), lambda snap: None)
    assert _sample(poller).rtt_ms is None


def test_audio_inbound_rows_do_not_drive_the_video_rate(monkeypatch):
    """`kind` is what separates the two; only video feeds the controller."""
    audio = _Entry(type="inbound-rtp", kind="audio",
                   bytesReceived=1_000_000, framesDecoded=0)
    poller = StatsPoller(_PeerConnection([audio], [audio]), lambda snap: None)
    _pin_clock(monkeypatch, 100.0, 101.0)
    _sample(poller)
    assert _sample(poller).bitrate_kbps is None


def test_an_unknown_stat_type_is_ignored():
    poller = StatsPoller(_PeerConnection([_Entry(type="transport")]),
                         lambda snap: None)
    assert _sample(poller).to_dict() == StatsSnapshot().to_dict()


def test_a_row_with_no_type_at_all_is_ignored():
    poller = StatsPoller(_PeerConnection([_Entry(bytesReceived=5)]),
                         lambda snap: None)
    assert _sample(poller).to_dict() == StatsSnapshot().to_dict()


# === Stopping ================================================================

def test_stopping_a_poller_that_never_started_is_harmless():
    poller = StatsPoller(_PeerConnection(), lambda snap: None)
    poller.stop()
    assert poller._stopped is True
    assert poller._task is None
