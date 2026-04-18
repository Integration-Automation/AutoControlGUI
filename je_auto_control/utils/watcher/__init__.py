"""Headless polling primitives for mouse position, pixel colour, and log tail."""
from je_auto_control.utils.watcher.watcher import (
    LogTail, MouseWatcher, PixelWatcher,
)

__all__ = ["LogTail", "MouseWatcher", "PixelWatcher"]
