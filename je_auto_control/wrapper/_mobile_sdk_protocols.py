"""Structural SDK contracts exported only through the lazy Android/iOS adapters."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from PIL.Image import Image


class AndroidSelector(Protocol):
    """uiautomator selector replies; JSON payloads remain explicit dynamic data."""
    @property
    def info(self) -> dict[str, Any]:
        """Return element metadata."""

    def wait(self, timeout: float) -> bool:
        """Wait for the selected element."""


class IOSSelector(Protocol):
    """WDA selector replies with native point bounds."""
    @property
    def bounds(self) -> object:
        """Return the SDK native bounds record."""

    def wait(self, timeout: float) -> IOSSelector | None:
        """Return the observed element or no match."""


class AndroidSDK(Protocol):
    """Reviewed uiautomator2 operations used by the framework; no dynamic attribute escape."""
    @property
    def info(self) -> dict[str, Any]:
        """Return native device metadata."""

    @property
    def clipboard(self) -> str:
        """Read device clipboard text."""

    def __call__(self, **selectors: str) -> AndroidSelector:
        """Build a widget selector."""

    def screenshot(self, filename: str | None = None) -> Image:
        """Read a native image, optionally saving it."""

    def click(self, x: int, y: int) -> None:
        """Tap a native pixel point."""

    def long_click(self, x: int, y: int, duration: float) -> None:
        """Hold a native point."""

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: float) -> None:
        """Swipe between native points."""

    def drag(self, x1: int, y1: int, x2: int, y2: int, duration: float) -> None:
        """Drag between native points."""

    def send_keys(self, text: str) -> None:
        """Send Unicode text."""

    def set_clipboard(self, text: str) -> None:
        """Write clipboard text."""

    def dump_hierarchy(self) -> str:
        """Read widget-tree XML."""

    def jsonrpc_call(self, method: str, params: object = None, timeout: float = 10) -> Any:
        """Invoke reviewed JSON RPC; the JSON response is dynamic data."""


class IOSSDK(Protocol):
    """Reviewed WDA operations; raw SDK implementation stays behind IOSDevice."""
    @property
    def orientation(self) -> str:
        """Read current orientation."""

    def __call__(self, **selectors: str) -> IOSSelector:
        """Build a native widget selector."""

    def window_size(self) -> tuple[int, int]:
        """Read the native viewport."""

    def _unsafe_window_size(self) -> tuple[int, int]:
        """Read viewport without SDK alert/Settings side effects."""

    def screenshot(self, filename: str | None = None) -> Image:
        """Read a native image, optionally saving it."""

    def tap(self, x: int, y: int) -> None:
        """Tap a UIKit point."""

    def tap_hold(self, x: int, y: int, duration: float) -> None:
        """Hold a UIKit point."""

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: float) -> None:
        """Swipe between UIKit points."""

    def send_keys(self, text: str) -> None:
        """Send native text."""

    def press(self, name: str) -> None:
        """Press a named device button."""

    def source(self) -> str:
        """Read the native accessibility source."""

    def _fetch(self, method: str, urlpath: str, data: object = None,
               with_session: bool = False, timeout: float | None = None) -> Any:
        """Bound an app-session JSON request at the SDK adapter boundary."""
