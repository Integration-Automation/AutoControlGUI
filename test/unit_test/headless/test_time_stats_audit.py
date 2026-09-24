"""Time / statistics defects from the 2026-09-24 audit.

A sequence jump stored every skipped number (and every seen number forever);
the SLO window counted records after ``now``; a UTC UNTIL was read as local
time for a naive DTSTART, and a huge INTERVAL overflowed; the latency digest
crashed on NaN and reported percentiles outside the recorded range; a lone
outlier among identical values scored 0; NaN corrupted percentiles; an
action on a frame boundary appeared in two snapshots; quiet_samples=0 called
a spike settled.
"""
import datetime as dt
import json

import pytest

from je_auto_control.utils.anomaly.anomaly import mad_anomalies
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.percentiles.percentiles import LatencyDigest
from je_auto_control.utils.recurrence.recurrence import occurrences, parse_rrule
from je_auto_control.utils.sequence_gap.sequence_gap import SequenceTracker
from je_auto_control.utils.settle_detector.settle_detector import settle_point
from je_auto_control.utils.slo.slo import evaluate_slo
from je_auto_control.utils.stats.stats import percentile
from je_auto_control.utils.time_travel.player import TimelinePlayer


def test_sequence_tracking_is_bounded_and_still_classifies():
    tracker = SequenceTracker(max_gap=10)
    assert tracker.observe("s", 5)["status"] == "ok"
    assert tracker.observe("s", 8)["missing"] == [6, 7]
    assert tracker.observe("s", 6)["status"] == "reorder"
    assert tracker.observe("s", 6)["status"] == "duplicate"
    assert tracker.observe("s", 8)["status"] == "duplicate"
    assert tracker.observe("s", 3)["status"] == "reorder"
    assert tracker.observe("s", 3)["status"] == "duplicate"
    with pytest.raises(ValueError, match="max_gap"):
        tracker.observe("s", 5_000_000)
    assert tracker.high_water("s") == 8


def test_the_slo_window_ends_at_now():
    records = [{"timestamp": 50, "ok": True}] + [
        {"timestamp": 200 + i, "ok": False} for i in range(10)]
    report = evaluate_slo(records, 0.99, window_s=100, now=100)
    assert (report["good"], report["total"]) == (1, 1)


def test_a_utc_until_is_converted_to_local_time_for_a_naive_start():
    start = dt.datetime(2024, 1, 1, 9)
    # Local 2024-01-03 09:00 written in UTC, as RFC 5545 requires for UNTIL.
    until_utc = dt.datetime(2024, 1, 3, 9).astimezone(dt.timezone.utc)
    rule = parse_rrule("FREQ=DAILY;UNTIL=" + until_utc.strftime("%Y%m%dT%H%M%SZ"))
    assert list(occurrences(rule, start))[-1] == dt.datetime(2024, 1, 3, 9)


def test_a_huge_interval_is_a_rule_error():
    with pytest.raises(AutoControlException, match="INTERVAL"):
        parse_rrule("FREQ=DAILY;INTERVAL=1000000000")


def test_the_latency_digest_refuses_non_finite_values_and_stays_in_range():
    digest = LatencyDigest()
    with pytest.raises(ValueError):
        digest.record(float("nan"))
    with pytest.raises(ValueError):
        digest.record(float("inf"))
    digest.record(1234.5)
    assert digest.percentile(99) == 1234.5
    negative = LatencyDigest()
    for value in (-5, -3, -1):
        negative.record(value)
    assert negative.percentile(50) == -1


def test_a_lone_outlier_among_identical_values_is_found():
    assert mad_anomalies([10, 10, 10, 10, 10, 10, 1000]) == [6]
    assert mad_anomalies([10, 10, 10]) == []


def test_percentile_refuses_nan():
    with pytest.raises(AutoControlException, match="NaN"):
        percentile([3, float("nan"), 1, 2], 50)


def test_an_action_on_a_frame_boundary_belongs_to_the_later_frame(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"entries": [
        {"timestamp": 1.0, "filename": "a.jpg"}, {"timestamp": 2.0, "filename": "b.jpg"}]}),
        encoding="utf-8")
    (tmp_path / "actions.jsonl").write_text(
        json.dumps({"timestamp": 2.0, "action_name": "AC_click"}) + "\n", encoding="utf-8")
    player = TimelinePlayer(tmp_path)
    assert player.at_step(0).actions == []
    assert [a.action_name for a in player.at_step(1).actions] == ["AC_click"]
    assert len(player.actions_in_window(1.0, 2.0)) == 1


def test_quiet_samples_must_be_positive():
    with pytest.raises(ValueError):
        settle_point([100, 100], quiet_samples=0)
