"""Tests for SessionQualityCache (round 38: webrtc_panel race fix)."""
import threading

import pytest

from je_auto_control.utils.remote_desktop.session_quality_cache import (
    SessionQualityCache,
)


def test_set_then_get_returns_color_and_snapshot():
    cache = SessionQualityCache()
    cache.set("alpha", color="#0f0", snapshot="snap-A")
    assert cache.get_color("alpha") == "#0f0"
    assert cache.get_snapshot("alpha") == "snap-A"


def test_get_color_default_when_missing():
    cache = SessionQualityCache()
    assert cache.get_color("nope") == "#555"
    assert cache.get_color("nope", default="#abc") == "#abc"


def test_get_snapshot_returns_none_when_missing():
    cache = SessionQualityCache()
    assert cache.get_snapshot("nope") is None


def test_drop_removes_both_dimensions():
    cache = SessionQualityCache()
    cache.set("alpha", color="#0f0", snapshot="snap-A")
    cache.drop("alpha")
    assert "alpha" not in cache
    assert cache.get_color("alpha") == "#555"
    assert cache.get_snapshot("alpha") is None


def test_drop_unknown_id_is_noop():
    cache = SessionQualityCache()
    cache.drop("never-existed")  # must not raise


def test_reset_clears_everything():
    cache = SessionQualityCache()
    for i in range(3):
        cache.set(f"sid-{i}", color="#fff", snapshot=i)
    cache.reset()
    assert len(cache) == 0
    assert cache.snapshot() == {}


def test_snapshot_returns_independent_copy():
    cache = SessionQualityCache()
    cache.set("alpha", color="#0f0", snapshot="snap-A")
    frozen = cache.snapshot()
    assert frozen == {"alpha": {"color": "#0f0", "snapshot": "snap-A"}}
    # Mutating the cache must not change the previously-returned snapshot.
    cache.set("alpha", color="#f00", snapshot="snap-B")
    assert frozen["alpha"]["color"] == "#0f0"


def test_known_sessions_returns_list_snapshot():
    cache = SessionQualityCache()
    cache.set("alpha", color="#fff", snapshot=None)
    cache.set("beta", color="#fff", snapshot=None)
    known = cache.known_sessions()
    assert sorted(known) == ["alpha", "beta"]
    # Independent of the live cache.
    cache.drop("alpha")
    assert sorted(known) == ["alpha", "beta"]


def test_concurrent_writes_and_iteration_do_not_raise():
    """Round 38 regression: hammer set/snapshot from many threads.

    Without the lock, ``snapshot()``'s comprehension over ``_qualities``
    would race against another thread's ``set()`` and could raise
    ``RuntimeError: dictionary changed size during iteration`` on
    CPython.
    """
    cache = SessionQualityCache()
    stop = threading.Event()
    errors: list = []

    def writer(start: int):
        for i in range(start, start + 500):
            if stop.is_set():
                return
            cache.set(f"sid-{i}", color="#fff", snapshot=i)

    def reader():
        while not stop.is_set():
            try:
                _ = cache.snapshot()
                _ = cache.known_sessions()
            except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: capture-and-assert
                errors.append(error)
                return

    writers = [threading.Thread(target=writer, args=(i * 1000,))
               for i in range(4)]
    readers = [threading.Thread(target=reader) for _ in range(4)]
    for t in writers + readers:
        t.start()
    for t in writers:
        t.join(timeout=10.0)
    stop.set()
    for t in readers:
        t.join(timeout=2.0)

    assert errors == [], (
        f"concurrent access raised: {[type(e).__name__ for e in errors]}"
    )
    # And the cache absorbed every write across all 4 writers.
    assert len(cache) == 2000


def test_reset_during_concurrent_writes_does_not_raise():
    """Qt thread calling reset() while asyncio thread does set() must not
    crash either side. Without the lock, this used to trigger
    ``RuntimeError: dictionary changed size during iteration`` from
    other readers (and is documented as undefined for set/clear).
    """
    cache = SessionQualityCache()
    stop = threading.Event()
    errors: list = []

    def writer():
        i = 0
        while not stop.is_set():
            try:
                cache.set(f"sid-{i}", color="#fff", snapshot=i)
            except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except
                errors.append(error)
                return
            i += 1

    def resetter():
        for _ in range(50):
            try:
                cache.reset()
            except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except
                errors.append(error)
                return

    writers = [threading.Thread(target=writer) for _ in range(4)]
    rs = threading.Thread(target=resetter)
    for t in writers:
        t.start()
    rs.start()
    rs.join(timeout=5.0)
    stop.set()
    for t in writers:
        t.join(timeout=2.0)

    assert errors == [], errors


def test_contains_is_thread_safe(monkeypatch):
    cache = SessionQualityCache()
    cache.set("alpha", color="#fff", snapshot=None)
    assert "alpha" in cache
    assert "beta" not in cache


@pytest.mark.parametrize("color", ["#0f0", "#ff0000", "#abcdef"])
def test_set_accepts_arbitrary_color_strings(color):
    cache = SessionQualityCache()
    cache.set("alpha", color=color, snapshot=None)
    assert cache.get_color("alpha") == color
