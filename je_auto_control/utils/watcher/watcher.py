"""Poll-based observers usable from a GUI timer or a standalone thread.

Each watcher exposes a ``sample()`` method that returns the latest reading
without side effects, so the same primitive can drive a HUD or a headless
monitor script.
"""
import collections
import logging
import threading
from typing import Deque, List, Optional, Tuple


class MouseWatcher:
    """Sample the current mouse position on demand."""

    def sample(self) -> Tuple[int, int]:
        """Return the current ``(x, y)``; raise ``RuntimeError`` on failure."""
        from je_auto_control.wrapper.auto_control_mouse import get_mouse_position
        try:
            x, y = get_mouse_position()
        except (OSError, RuntimeError, ValueError, TypeError) as error:
            raise RuntimeError(f"MouseWatcher.sample failed: {error!r}") from error
        return int(x), int(y)


class PixelWatcher:
    """Sample the pixel colour at an arbitrary coordinate."""

    def sample(self, x: int, y: int) -> Optional[Tuple[int, int, int]]:
        """Return ``(r, g, b)`` at ``(x, y)``, or ``None`` on failure."""
        from je_auto_control.wrapper.auto_control_screen import get_pixel
        try:
            raw = get_pixel(int(x), int(y))
        except (OSError, RuntimeError, ValueError, TypeError):
            return None
        if raw is None or len(raw) < 3:
            return None
        return int(raw[0]), int(raw[1]), int(raw[2])


class LogTail(logging.Handler):
    """A ring buffer of recent log messages, suitable for live display."""

    def __init__(self, capacity: int = 200,
                 level: int = logging.INFO) -> None:
        super().__init__(level=level)
        self._buffer: Deque[str] = collections.deque(maxlen=max(10, int(capacity)))
        self._lock = threading.Lock()
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            text = self.format(record)
        except (ValueError, TypeError):
            text = record.getMessage()
        with self._lock:
            self._buffer.append(text)

    def snapshot(self) -> List[str]:
        """Return a copy of the current buffer (oldest first)."""
        with self._lock:
            return list(self._buffer)

    def attach(self, logger: logging.Logger) -> None:
        """Install this tail on ``logger`` (idempotent)."""
        if self not in logger.handlers:
            logger.addHandler(self)

    def detach(self, logger: logging.Logger) -> None:
        """Remove this tail from ``logger``."""
        if self in logger.handlers:
            logger.removeHandler(self)
