"""The wire between this process and the libei helper process.

:mod:`ei_worker` runs the libei session in a child so that whatever libei
does on teardown, it does to a process nobody else lives in. This module is
everything the two sides have to agree on, and nothing else: how a message is
framed, how large one may be, what an event looks like in transit, and what
each failure is called.

**Bounded on purpose.** A frame is a 4-byte big-endian length and that many
bytes of UTF-8 JSON, capped at :data:`MAX_FRAME_BYTES`; a batch carries at
most :data:`MAX_BATCH` events. Neither side will read a length it has not
checked, so a corrupted stream ends in :class:`EiProtocolError` rather than
in an allocation sized by garbage — and the child is driving someone's
desktop, so "it tried its best with a bad frame" is not an option.

**Two families of failure**, split by the one question the caller has to
answer — may another backend redo this?

:class:`EiWorkerError` is a ``LibeiUnavailable``: nothing reached the desktop,
so the ydotool path may take the action over, exactly as it does when the
in-process backend refuses.

:class:`EiRequestUncertain` is *not*: the request was written and its fate is
unknown (a timeout, a cancellation, a worker that died mid-batch). Replaying
it through another backend could type the key twice, so these reach the
caller instead.
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from typing import (
    Any, BinaryIO, Dict, List, Mapping, Optional, Sequence, Tuple,
)

from je_auto_control.linux_wayland.input_events import (
    EV_ABS, EV_KEY, EV_REL, EV_SYN, InputEvent,
)
from je_auto_control.linux_wayland.libei import LibeiUnavailable
from je_auto_control.utils.exception.exceptions import AutoControlException

#: Most events one request may carry. A chord is a handful; a pointer move is
#: three. Anything longer should be several requests, each cancellable.
MAX_BATCH = 64

#: Largest frame either side will write or accept.
MAX_FRAME_BYTES = 64 * 1024

#: The capability that is unavailable when the worker cannot serve.
CAPABILITY = "input"

# The evdev codes both sides have to read the same way.
ABS_X = 0x00
ABS_Y = 0x01
REL_HWHEEL = 0x06
REL_WHEEL = 0x08

#: ``BTN_MOUSE`` .. ``BTN_TASK``: the ``EV_KEY`` codes that are pointer
#: buttons, and so go to libei's button entry point rather than its key one.
BUTTON_CODES = range(0x110, 0x118)

#: One held key or button: ``("key" | "button", code)``.
Held = Tuple[str, int]

_LENGTH = struct.Struct(">I")
_EVENT_TYPES = frozenset({EV_SYN, EV_KEY, EV_REL, EV_ABS})
_INT32 = 2 ** 31


class EiWorkerError(LibeiUnavailable):
    """The helper could not serve, and nothing was sent to the desktop."""

    capability = CAPABILITY


class EiDependencyMissing(EiWorkerError):
    """The helper started but a library it needs is not installed."""

    def __init__(self, dependency: str, message: str = "") -> None:
        self.dependency = dependency
        super().__init__(
            message or f"{dependency} is not installed, so the libei helper "
                       f"cannot provide {CAPABILITY}")


class EiProtocolError(EiWorkerError):
    """A frame or batch broke the limits or the format; it was not applied."""


class EiEmitRefused(EiWorkerError):
    """libei, in the helper, refused this emission (a paused device, a point
    outside every region). The same refusal the in-process backend gives."""


class EiRequestUncertain(AutoControlException):
    """A request was written and what it did to the desktop is not known."""

    capability = CAPABILITY


class EiWorkerTimeout(EiRequestUncertain):
    """No acknowledgement arrived within the caller's deadline."""


class EiWorkerCancelled(EiRequestUncertain):
    """The caller cancelled; ``applied`` is how far the batch got, if known."""

    def __init__(self, message: str, applied: Optional[int] = None) -> None:
        self.applied = applied
        super().__init__(message)


class EiWorkerDied(EiRequestUncertain):
    """The helper process ended; ``pressed_keys`` were down when it did."""

    def __init__(self, message: str, returncode: Optional[int] = None,
                 pressed_keys: Sequence[int] = ()) -> None:
        self.returncode = returncode
        self.pressed_keys = tuple(pressed_keys)
        super().__init__(message)


@dataclass(frozen=True)
class InputAck:
    """The helper's answer to one batch."""

    request_id: int
    #: How many of the batch's events were applied.
    applied: int
    #: Round trip as the caller saw it, in seconds.
    elapsed_s: float = 0.0
    cancelled: bool = False


def write_frame(stream: BinaryIO, message: Mapping[str, Any]) -> None:
    """Write one message and flush it.

    :raises EiProtocolError: the encoded message exceeds the frame limit.
    """
    payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_FRAME_BYTES:
        raise EiProtocolError(
            f"a {len(payload)}-byte frame exceeds the {MAX_FRAME_BYTES}-byte "
            "limit")
    stream.write(_LENGTH.pack(len(payload)) + payload)
    stream.flush()


def _read_exactly(stream: BinaryIO, count: int) -> bytes:
    """Read ``count`` bytes, or fewer only if the stream ended."""
    chunks: List[bytes] = []
    remaining = count
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_frame(stream: BinaryIO) -> Optional[Dict[str, Any]]:
    """Read one message; None when the stream ended between messages.

    :raises EiProtocolError: an oversized length, a truncated frame, or a
        payload that is not a JSON object.
    """
    header = _read_exactly(stream, _LENGTH.size)
    if not header:
        return None
    if len(header) < _LENGTH.size:
        raise EiProtocolError("the stream ended inside a frame header")
    (length,) = _LENGTH.unpack(header)
    if length > MAX_FRAME_BYTES:
        raise EiProtocolError(
            f"a frame announced {length} bytes, over the {MAX_FRAME_BYTES}-"
            "byte limit")
    payload = _read_exactly(stream, length)
    if len(payload) < length:
        raise EiProtocolError("the stream ended inside a frame")
    try:
        message = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise EiProtocolError(f"a frame was not valid JSON: {error}") from error
    if not isinstance(message, dict):
        raise EiProtocolError("a frame was not a JSON object")
    return message


def encode_batch(batch: Sequence[InputEvent]) -> List[List[int]]:
    """Turn a batch into its wire form, enforcing the batch limit.

    :raises EiProtocolError: the batch is empty, too long, or holds an event
        that is not a valid evdev triple.
    """
    if not batch:
        raise EiProtocolError("an empty batch has nothing to send")
    if len(batch) > MAX_BATCH:
        raise EiProtocolError(
            f"a batch of {len(batch)} events exceeds the limit of "
            f"{MAX_BATCH}; send it as several requests")
    return [list(_checked(event.type, event.code, event.value))
            for event in batch]


def decode_batch(raw: Any) -> List[InputEvent]:
    """Rebuild a batch from its wire form, with the same checks.

    The helper validates everything before applying anything, so a bad batch
    is refused whole rather than half-typed.
    """
    if not isinstance(raw, list) or not raw:
        raise EiProtocolError("a batch must be a non-empty list of events")
    if len(raw) > MAX_BATCH:
        raise EiProtocolError(
            f"a batch of {len(raw)} events exceeds the limit of {MAX_BATCH}")
    events = []
    for item in raw:
        if not isinstance(item, list) or len(item) != 3:
            raise EiProtocolError(f"not an event triple: {item!r}")
        events.append(InputEvent(*_checked(*item)))
    return events


def _checked(kind: Any, code: Any, value: Any) -> Tuple[int, int, int]:
    """One event's three fields, or a refusal naming what is wrong."""
    for part in (kind, code, value):
        if isinstance(part, bool) or not isinstance(part, int):
            raise EiProtocolError(
                f"event fields must be integers, got {part!r}")
    if kind not in _EVENT_TYPES:
        raise EiProtocolError(f"unsupported event type {kind}")
    if not 0 <= code < 0x10000 or not -_INT32 <= value < _INT32:
        raise EiProtocolError(
            f"event ({kind}, {code}, {value}) is out of range")
    return kind, code, value


__all__ = [
    "ABS_X", "ABS_Y", "BUTTON_CODES", "Held", "REL_HWHEEL", "REL_WHEEL",
    "CAPABILITY", "EiDependencyMissing", "EiEmitRefused", "EiProtocolError",
    "EiRequestUncertain", "EiWorkerCancelled", "EiWorkerDied",
    "EiWorkerError", "EiWorkerTimeout", "InputAck", "MAX_BATCH",
    "MAX_FRAME_BYTES", "decode_batch", "encode_batch", "read_frame",
    "write_frame",
]
