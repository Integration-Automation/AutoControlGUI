"""Observation / state defects from the 2026-09-24 audit (fakes only).

The emergency stop could not wake a sleeping main thread, fired on a stale
press and worked only once; crowded set-of-marks labels overlapped or went
off-screen; "${a.${b}}" left a literal placeholder; lock waits overran their
timeout; a manual poll racing the observer thread fired twice; CloudEvents
without source/type or with bytes were built; zero-size coordinate spaces
divided by zero; a list vs tuple bbox counted as a move.
"""
import datetime
import threading
import time

import pytest

from je_auto_control.utils.coordinate_space.coordinate_space import CoordinateSpace, xga_space
from je_auto_control.utils.critical_exit import critical_exit
from je_auto_control.utils.events.cloud_events import to_cloudevent
from je_auto_control.utils.lock_session.lock_session import _wait_lock_state
from je_auto_control.utils.marks_layout.marks_layout import place_labels
from je_auto_control.utils.observer.observer import ScreenObserver
from je_auto_control.utils.screen_state.screen_state import diff_snapshots
from je_auto_control.utils.script_vars.interpolate import interpolate_value


def test_the_emergency_stop_wakes_a_sleeping_main_thread():
    threading.Timer(0.2, critical_exit._interrupt_main).start()
    started = time.monotonic()
    with pytest.raises(KeyboardInterrupt):
        time.sleep(3)
    assert time.monotonic() - started < 2.0


def test_the_listener_ignores_a_stale_press_and_arms_again(monkeypatch):
    reads = iter([True, False, True, False, False, True, False] + [False] * 1000)
    fired = []
    monkeypatch.setattr(critical_exit.keyboard_check, "check_key_is_press", lambda _k: next(reads))
    monkeypatch.setattr(critical_exit, "_interrupt_main", lambda: fired.append(1))
    monkeypatch.setattr(critical_exit, "_POLL_INTERVAL_SECONDS", 0.001)
    listener = critical_exit.CriticalExit()
    listener.start()
    time.sleep(0.3)
    listener.stop()
    listener.join(2)
    assert len(fired) == 2   # the stale first read is skipped; two real presses fire


def test_crowded_labels_never_overlap_or_leave_the_screen():
    marks = [{"id": n, "bbox": [10, 10, 40, 20]} for n in range(4)]
    labels = [entry["label"] for entry in place_labels(marks, bounds=(100, 100))]
    for i, first in enumerate(labels):
        assert first[0] >= 0 and first[1] >= 0
        for second in labels[i + 1:]:
            assert (first[0] + first[2] <= second[0] or second[0] + second[2] <= first[0]
                    or first[1] + first[3] <= second[1] or second[1] + second[3] <= first[1])
    top = place_labels([{"id": 1, "bbox": [0, 0, 40, 20]}])[0]["label"]
    assert top[1] >= 0


def test_a_nested_placeholder_is_an_error():
    with pytest.raises(ValueError, match="nested"):
        interpolate_value("${a.${b}}", {"a": {"b": 1}, "b": "b"})
    assert interpolate_value("Total: $${n}", {"n": 5}) == "Total: $5"


def test_a_lock_wait_ends_at_its_deadline():
    now = [0.0]
    slept = []

    def sleep(seconds):
        slept.append(seconds)
        now[0] += seconds

    result = _wait_lock_state(False, probe=lambda: True, timeout_s=1.0, interval_s=30.0,
                              clock=lambda: now[0], sleep=sleep)
    assert result is False and max(slept) <= 1.0


def test_polls_never_evaluate_a_rule_concurrently():
    observer = ScreenObserver(poll_interval_s=10)
    gate = threading.Barrier(2)
    active, peak = [0], [0]
    lock = threading.Lock()

    def predicate():
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.1)
        with lock:
            active[0] -= 1
        return True

    observer.add("r", predicate, lambda *_a: None, events=("appear",))
    threads = [threading.Thread(target=lambda: (gate.wait(), observer.poll_once())) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert peak[0] == 1   # two overlapping evaluations could both fire one transition


def test_cloudevents_follow_the_spec():
    with pytest.raises(ValueError):
        to_cloudevent("", "src", {})
    with pytest.raises(ValueError):
        to_cloudevent("t", "src", {}, time="yesterday")
    binary = to_cloudevent("t", "src", b"\x00\x01")
    assert binary["data_base64"] == "AAE=" and "data" not in binary
    stamp = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc).isoformat()
    assert to_cloudevent("t", "src", {}, time=stamp)["time"] == stamp


def test_coordinate_spaces_need_positive_sizes():
    with pytest.raises(ValueError):
        CoordinateSpace(1920, 1080, 0, 0)
    with pytest.raises(ValueError):
        xga_space(0, 1080)


def test_the_same_box_in_another_container_is_not_a_move():
    before = [{"role": "button", "name": "OK", "bbox": [0, 0, 10, 10]}]
    after = [{"role": "button", "name": "OK", "bbox": (0, 0, 10, 10.0000001)}]
    assert diff_snapshots(before, after)["moved"] == []
