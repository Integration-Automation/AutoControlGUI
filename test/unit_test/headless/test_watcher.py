"""Tests for the watcher module (MouseWatcher, PixelWatcher, LogTail)."""
import logging

import pytest

from je_auto_control.utils.watcher.watcher import (
    LogTail, MouseWatcher, PixelWatcher,
)


def test_log_tail_buffers_messages():
    tail = LogTail(capacity=10)
    logger = logging.getLogger("je_auto_control.test_log_tail")
    logger.setLevel(logging.INFO)
    tail.attach(logger)
    try:
        for i in range(30):
            logger.info("msg %d", i)
    finally:
        tail.detach(logger)
    snap = tail.snapshot()
    assert len(snap) == 10
    assert "msg 29" in snap[-1]
    assert "msg 20" in snap[0]


def test_log_tail_attach_detach_idempotent():
    tail = LogTail()
    logger = logging.getLogger("je_auto_control.test_attach")
    tail.attach(logger)
    tail.attach(logger)
    assert logger.handlers.count(tail) == 1
    tail.detach(logger)
    tail.detach(logger)
    assert tail not in logger.handlers


def test_mouse_watcher_reports_failure(monkeypatch):
    def broken():
        raise OSError("nope")
    import je_auto_control.wrapper.auto_control_mouse as mouse_mod
    monkeypatch.setattr(mouse_mod, "get_mouse_position", broken)
    with pytest.raises(RuntimeError):
        MouseWatcher().sample()


def test_pixel_watcher_returns_none_on_error(monkeypatch):
    import je_auto_control.wrapper.auto_control_screen as screen_mod

    def _raise_os_error(_x, _y):
        raise OSError("nope")

    monkeypatch.setattr(screen_mod, "get_pixel", _raise_os_error)
    assert PixelWatcher().sample(0, 0) is None


def test_pixel_watcher_normalises_rgb(monkeypatch):
    import je_auto_control.wrapper.auto_control_screen as screen_mod
    monkeypatch.setattr(screen_mod, "get_pixel",
                        lambda x, y: (12, 34, 56, 255))
    assert PixelWatcher().sample(1, 1) == (12, 34, 56)
