"""Tests for wait_until_window_closed (injectable finder, no real windows)."""
import pytest

from je_auto_control.utils.smart_waits.waits import wait_until_window_closed


def test_succeeds_when_window_disappears():
    state = {"n": 0}

    def finder(title, case_sensitive):
        state["n"] += 1
        return state["n"] < 3  # present for two checks, then gone

    outcome = wait_until_window_closed(
        "Editor", timeout_s=2.0, poll_interval_s=0.001, finder=finder,
    )
    assert outcome.succeeded is True
    assert outcome.reason == "window closed"


def test_times_out_when_window_stays_open():
    outcome = wait_until_window_closed(
        "Editor", timeout_s=0.1, poll_interval_s=0.02,
        finder=lambda title, cs: True,
    )
    assert outcome.succeeded is False
    assert "timeout" in outcome.reason


def test_succeeds_immediately_when_already_absent():
    outcome = wait_until_window_closed(
        "Gone", timeout_s=1.0, poll_interval_s=0.001,
        finder=lambda title, cs: False,
    )
    assert outcome.succeeded is True


def test_rejects_non_positive_timeout():
    with pytest.raises(ValueError):
        wait_until_window_closed("x", timeout_s=0, finder=lambda t, cs: False)
