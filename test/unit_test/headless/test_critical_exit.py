"""Headless tests for the CriticalExit panic-key listener.

The listener is a safety device: it is what a user reaches for when a script
has seized the mouse. Every test here guards a way it could fail *silently*,
because a panic key that quietly does nothing is worse than none at all.

No test injects real input. ``check_key_is_press`` is always stubbed so the
suite never depends on — or disturbs — the real keyboard, and
``interrupt_main`` is always stubbed so a test can never interrupt pytest.
"""
import _thread
import time

import pytest

from je_auto_control.utils.critical_exit import critical_exit as critical_exit_module
from je_auto_control.utils.critical_exit.critical_exit import CriticalExit
from je_auto_control.utils.exception.exceptions import (
    AutoControlCantFindKeyException,
)


@pytest.fixture()
def never_pressed(monkeypatch):
    """Stub the keyboard poll so the exit key is never seen as pressed."""
    monkeypatch.setattr(
        critical_exit_module.keyboard_check, "check_key_is_press",
        lambda _keycode: False,
    )


@pytest.fixture()
def no_real_interrupt(monkeypatch):
    """Stub interrupt_main and count calls, so pytest is never interrupted."""
    calls = {"count": 0}

    def _fake_interrupt():
        calls["count"] += 1

    monkeypatch.setattr(_thread, "interrupt_main", _fake_interrupt)
    return calls


def test_unknown_key_name_raises_instead_of_dying_silently():
    """A typo'd key name must fail fast at set time.

    Regression: the name was resolved with ``dict.get``, so a typo stored
    ``None``; the listener then raised TypeError on its first poll, which the
    ``except`` clause did not catch. The thread died and the panic key was
    silently dead.
    """
    listener = CriticalExit()
    with pytest.raises(AutoControlCantFindKeyException):
        listener.set_critical_key("f77")


def test_failed_set_leaves_the_previous_key_intact():
    """A rejected key must not clobber the working default."""
    listener = CriticalExit()
    original = listener._exit_check_key
    with pytest.raises(AutoControlCantFindKeyException):
        listener.set_critical_key("not_a_key")
    assert listener._exit_check_key == original


def test_set_critical_key_accepts_name_and_keycode():
    listener = CriticalExit()
    listener.set_critical_key("f2")
    by_name = listener._exit_check_key
    assert by_name is not None

    listener.set_critical_key(by_name)
    assert listener._exit_check_key == by_name


def test_set_critical_key_none_leaves_key_unchanged():
    listener = CriticalExit()
    before = listener._exit_check_key
    listener.set_critical_key(None)
    assert listener._exit_check_key == before


def test_listener_stops_on_request(never_pressed):
    """stop() must end the loop; without it the thread was unstoppable."""
    listener = CriticalExit()
    listener.init_critical_exit()
    assert listener.is_alive()
    listener.stop()
    listener.join(2.0)
    assert not listener.is_alive()


def test_listener_polls_at_an_interval_rather_than_busy_spinning(monkeypatch):
    """The poll loop must throttle.

    Regression: ``while True:`` with no sleep pegged a CPU core (measured at
    ~92% of one core). Asserting on a call count is stable in CI, where a
    direct CPU-time assertion would be flaky.
    """
    calls = {"count": 0}

    def _counting_poll(_keycode):
        calls["count"] += 1
        return False

    monkeypatch.setattr(
        critical_exit_module.keyboard_check, "check_key_is_press",
        _counting_poll,
    )
    listener = CriticalExit()
    listener.init_critical_exit()
    time.sleep(0.2)
    listener.stop()
    listener.join(2.0)

    # ~10 polls expected at a 20ms interval. A busy-spin reaches many
    # thousands; the ceiling is loose enough to tolerate a slow CI box.
    assert 0 < calls["count"] < 500


def test_interrupt_fires_once_and_then_stops(monkeypatch, no_real_interrupt):
    """A held key must not flood the main thread with interrupts.

    Regression: the loop re-fired every iteration for as long as the key was
    held, which could interrupt the main thread's own KeyboardInterrupt
    handler and its cleanup.
    """
    monkeypatch.setattr(
        critical_exit_module.keyboard_check, "check_key_is_press",
        lambda _keycode: True,          # key held down for the whole test
    )
    listener = CriticalExit()
    listener.init_critical_exit()
    listener.join(2.0)

    assert not listener.is_alive()
    assert no_real_interrupt["count"] == 1
