"""Scope locator versions and keep detection evidence separate from verification."""
from __future__ import annotations

import contextvars
import hashlib
import io
from contextlib import contextmanager
from typing import Dict, Iterator, Optional, TYPE_CHECKING

from je_auto_control.utils.action_journal.events import JSONValue

if TYPE_CHECKING:
    from PIL import Image

_VERSION: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('healing_version', default=None)
_LOCATOR: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('healing_locator_id', default=None)
_EVIDENCE: contextvars.ContextVar[Optional[Dict[str, JSONValue]]] = contextvars.ContextVar(
    'healing_capture_evidence', default=None)


@contextmanager
def attempt_evidence() -> Iterator[None]:
    """Keep capture identities isolated to a single runtime attempt."""
    token = _EVIDENCE.set({})
    try:
        yield
    finally:
        _EVIDENCE.reset(token)


def record_frame(frame: bytes, method: str, backend: Optional[str], model: Optional[str] = None) -> None:
    """Record actual consumed bytes only during an active healing attempt."""
    evidence = _EVIDENCE.get()
    if evidence is None:
        return
    detail: Dict[str, JSONValue] = {'frame_hash': hashlib.sha256(frame).hexdigest(),
                                  'backend': backend, 'model': model, 'cost': None}
    evidence[method] = detail
    evidence.update(detail)


def record_image_frame(image: Image.Image) -> None:
    """Serialize an existing image for provenance without taking another capture."""
    if _EVIDENCE.get() is not None:
        output = io.BytesIO()
        image.save(output, format='PNG')
        record_frame(output.getvalue(), 'image', 'opencv')


@contextmanager
def healing_context(locator_version: str, *, locator_id: Optional[str] = None) -> Iterator[None]:
    """Annotate runtime attempts without turning detection into operation verification."""
    version, locator = _VERSION.set(locator_version), _LOCATOR.set(locator_id)
    try:
        yield
    finally:
        _LOCATOR.reset(locator)
        _VERSION.reset(version)


def event_context(method: str, found: bool, durations: Optional[Dict[str, float]]) -> Dict[str, JSONValue]:
    """Collect declared version, current action IDs and available strategy timings."""
    # pylint: disable-next=import-outside-toplevel  # reason: audit context is read after executor registration
    from je_auto_control.utils.action_journal.store import current_journal_context
    return {**current_journal_context(), 'locator_id': _LOCATOR.get(),
            'selected_strategy': method, 'detection_found': found, 'verified_success': None,
            'frame_hash': None, 'backend': None, 'model': None, 'cost': None,
            'strategy_durations_ms': dict(durations) if durations else None,
            **(_EVIDENCE.get() or {})}


def bound_locator_version() -> Optional[str]:
    """The version bound to this attempt, or unknown for an unversioned call."""
    return _VERSION.get()
