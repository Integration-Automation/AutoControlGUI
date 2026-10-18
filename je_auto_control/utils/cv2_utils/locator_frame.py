"""Lazy run-local capture and provenance shared by image and VLM locators."""
from __future__ import annotations

import io
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from hashlib import sha256
from math import floor
from threading import Lock
from time import monotonic
from typing import Any, Iterator, Optional, Sequence

from je_auto_control.utils.cv2_utils.screenshot import _validate_region
from je_auto_control.utils.exception.exceptions import AutoControlScreenException
from je_auto_control.utils.monitor_layout import logical_frame


@dataclass(frozen=True)
class LocatorFrame:
    """Owned PNG pixels in logical pointer units and their actual clipped origin."""

    png: bytes = field(repr=False)
    origin: tuple[int, int]
    size: tuple[int, int]

    def image(self) -> Any:
        """Return a detached Pillow copy, so consumers cannot mutate the shared PNG."""
        # pylint: disable-next=import-outside-toplevel  # reason: image decoders initialize only when pixels are requested
        from PIL import Image
        with Image.open(io.BytesIO(self.png)) as image:
            return image.copy()

    def to_screen(self, point: tuple[int, int]) -> Optional[tuple[int, int]]:
        """Reject out-of-frame replies and translate once, including negative origins."""
        x, y = point
        if not 0 <= x < self.size[0] or not 0 <= y < self.size[1]:
            return None
        return floor(self.origin[0] + x), floor(self.origin[1] + y)


# pylint: disable-next=too-many-instance-attributes  # reason: one attempt's capture/provenance fields and lock
class LocatorFrameOwner:
    """Capture once on demand, sharing either the PNG or the original capture failure."""

    def __init__(self, screen_region: Optional[Sequence[int]], *, all_screens: bool) -> None:
        self.region: Optional[list[int]] = None
        if screen_region is not None:
            _validate_region(list(screen_region))
            self.region = [int(value) for value in screen_region]
        self.all_screens = all_screens
        self._lock = Lock()
        self._frame: Optional[LocatorFrame] = None
        self._failure: Optional[Exception] = None
        self._closed = False
        self.capture_ms: Optional[float] = None
        self.template_hash: Optional[str] = None
        self.backend: Optional[str] = None
        self.model: Optional[str] = None

    @property
    def captured(self) -> Optional[LocatorFrame]:
        """Inspect provenance without capturing for telemetry or test doubles."""
        return self._frame

    def snapshot(self) -> LocatorFrame:
        """Get the same pixels or raise the same failure on every read in this attempt."""
        with self._lock:
            if self._closed:
                raise AutoControlScreenException("locator frame scope is closed")
            if self._failure is not None:
                raise self._failure
            if self._frame is None:
                started = monotonic()
                try:
                    self._frame = self._capture()
                except Exception as error:  # reason: cache and re-raise; never retry capture as locator fallback
                    self._failure = error
                    raise
                finally:
                    self.capture_ms = (monotonic() - started) * 1000
            return self._frame

    def _capture(self) -> LocatorFrame:
        region = None
        if self.region is not None:
            left, top, right, bottom = self.region
            region = (left, top, right - left, bottom - top)
        image, x, y = logical_frame.grab_logical(region, all_screens=self.all_screens)
        try:
            stream = io.BytesIO()
            image.save(stream, format="PNG")
            return LocatorFrame(stream.getvalue(), (x, y), image.size)
        finally:
            image.close()

    def record_template(self, template: Any) -> None:
        """Fingerprint decoded template pixels and layout, not mutable path names."""
        if self.template_hash is not None:
            return
        digest = sha256()
        digest.update(str((template.shape, str(template.dtype))).encode("utf-8"))
        digest.update(template.tobytes())
        self.template_hash = digest.hexdigest()

    def record_backend(self, name: str, model: Optional[str]) -> None:
        """Record the selected backend/model without inferring token usage or cost."""
        self.backend, self.model = name, model

    def clear(self) -> None:
        """Drop screenshots and cached exception cycles even while an error propagates."""
        with self._lock:
            self._frame = None
            self._failure = None
            self._closed = True


_CURRENT: ContextVar[Optional[LocatorFrameOwner]] = ContextVar("je_auto_control_locator_frame", default=None)


def current_locator_frame() -> Optional[LocatorFrameOwner]:
    """Return the current attempt's lazy owner; ordinary locator calls remain unbound."""
    return _CURRENT.get()


@contextmanager
def locator_frame_scope(screen_region: Optional[Sequence[int]], *,
                         all_screens: bool) -> Iterator[LocatorFrameOwner]:
    """Bind independent nested/concurrent attempts and release their pixels on exit."""
    owner = LocatorFrameOwner(screen_region, all_screens=all_screens)
    token = _CURRENT.set(owner)
    try:
        yield owner
    finally:
        _CURRENT.reset(token)
        owner.clear()
