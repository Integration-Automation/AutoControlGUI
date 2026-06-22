"""Tests for wait_until_clipboard_changes (injectable reader, no real OS)."""
import pytest

from je_auto_control.utils.smart_waits.waits import (
    wait_until_clipboard_changes,
)


def _reader_seq(values):
    """A reader yielding each value once, then repeating the last."""
    seq = list(values)

    def read():
        return seq.pop(0) if len(seq) > 1 else seq[0]

    return read


def test_succeeds_when_clipboard_changes():
    outcome = wait_until_clipboard_changes(
        timeout_s=2.0, poll_interval_s=0.001,
        reader=_reader_seq(["old", "old", "new"]),
    )
    assert outcome.succeeded is True
    assert outcome.reason == "clipboard changed"


def test_baseline_override_detects_difference():
    outcome = wait_until_clipboard_changes(
        baseline="something-else", timeout_s=1.0, poll_interval_s=0.001,
        reader=_reader_seq(["current"]),
    )
    assert outcome.succeeded is True


def test_target_equals_match():
    outcome = wait_until_clipboard_changes(
        target="DONE", timeout_s=2.0, poll_interval_s=0.001,
        reader=_reader_seq(["nope", "nope", "DONE"]),
    )
    assert outcome.succeeded is True


def test_target_contains_match():
    outcome = wait_until_clipboard_changes(
        target="DONE", contains=True, timeout_s=2.0, poll_interval_s=0.001,
        reader=_reader_seq(["nope", "hello DONE world"]),
    )
    assert outcome.succeeded is True


def test_times_out_when_unchanged():
    outcome = wait_until_clipboard_changes(
        timeout_s=0.1, poll_interval_s=0.02, reader=lambda: "static",
    )
    assert outcome.succeeded is False
    assert "timeout" in outcome.reason


def test_rejects_non_positive_timeout():
    with pytest.raises(ValueError):
        wait_until_clipboard_changes(timeout_s=0, reader=lambda: "x")
