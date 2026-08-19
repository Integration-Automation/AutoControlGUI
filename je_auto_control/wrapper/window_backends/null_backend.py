"""Fallback window backend for a platform with no implementation."""
from typing import List, Tuple

from je_auto_control.wrapper.window_backends.base import WindowManageBackend


class NullWindowBackend(WindowManageBackend):
    """Answers every operation with a refusal that says why.

    ``list_windows`` returns an empty list rather than raising: "there are no
    windows I can see" is a truthful answer that lets a caller iterate, and
    every operation that would *act* on a window still refuses loudly.
    """

    name = "null"

    def __init__(self, reason: str = "") -> None:
        self.available = False
        self.reason = reason or "no window backend for this platform"
        self.name = f"null ({self.reason})"

    def list_windows(self) -> List[Tuple[int, str]]:
        return []
