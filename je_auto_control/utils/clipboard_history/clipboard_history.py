"""Clipboard history — a capped ring buffer with a background poller.

AutoControl can get/set the *current* clipboard but keeps no history. This
records the last ``capacity`` distinct text entries (newest first) and can
poll the clipboard on a background thread to capture entries as they change
— so a flow can recall or search what was copied earlier.

Pure standard library; the clipboard backend is imported lazily so the ring
buffer (``add`` / ``snapshot`` / ``search`` / ``get``) is unit-testable
without a real clipboard. Thread-safe.
"""
import threading
from typing import List, Optional


class ClipboardHistory:
    """A capped, newest-first history of distinct clipboard text entries."""

    def __init__(self, capacity: int = 50, poll_interval_s: float = 1.0
                 ) -> None:
        self._capacity = max(1, int(capacity))
        self._poll = max(0.05, float(poll_interval_s))
        self._items: List[str] = []
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def add(self, text: str) -> bool:
        """Record ``text`` (newest first); skip empty or unchanged-top.

        Returns whether it was added.
        """
        if not text:
            return False
        with self._lock:
            if self._items and self._items[0] == text:
                return False
            if text in self._items:
                self._items.remove(text)
            self._items.insert(0, text)
            del self._items[self._capacity:]
            return True

    def snapshot(self) -> List[str]:
        """Return the history, newest first."""
        with self._lock:
            return list(self._items)

    def get(self, index: int = 0) -> Optional[str]:
        """Return the entry at ``index`` (0 = most recent) or ``None``."""
        with self._lock:
            if 0 <= index < len(self._items):
                return self._items[index]
        return None

    def search(self, query: str) -> List[str]:
        """Return entries containing ``query`` (case-insensitive)."""
        needle = str(query).lower()
        with self._lock:
            return [item for item in self._items if needle in item.lower()]

    def clear(self) -> None:
        """Drop all history."""
        with self._lock:
            self._items.clear()

    @property
    def running(self) -> bool:
        """Whether the background poll thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    def capture_once(self) -> bool:
        """Read the live clipboard once and record it; return whether added."""
        from je_auto_control.utils.clipboard.clipboard import get_clipboard
        try:
            return self.add(get_clipboard())
        except (OSError, RuntimeError, ValueError):
            return False

    def start(self) -> None:
        """Start polling the clipboard on a background thread (idempotent)."""
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="clipboard-history", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Signal the poll thread to stop and join it."""
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=float(timeout))
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.capture_once()
            self._stop.wait(self._poll)


default_clipboard_history = ClipboardHistory()
