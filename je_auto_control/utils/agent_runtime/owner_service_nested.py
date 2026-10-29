"""The nested grant a Linux owner-service helper receives once on fd 4."""
from __future__ import annotations

import os
import struct
from dataclasses import dataclass

from je_auto_control.utils.agent_runtime import owner_service_wire as wire
from je_auto_control.utils.agent_runtime.errors import AgentTaskError

BOOTSTRAP_FD = 4
BOOTSTRAP_MAGIC = 0x4143424E
BOOTSTRAP_VERSION = 1
# owner_nested_bootstrap in owner_internal.h: magic, version, parent ticket, capability.
_FRAME = struct.Struct("<II16s16s32s")


@dataclass(frozen=True)
class NestedGrant:
    """Names the parent record and carries its capability. It authorizes nothing alone:
    the service still requires the payload principal inside the parent's payload."""

    parent: wire.Ticket
    capability: bytes

    def __repr__(self) -> str:
        return f"NestedGrant(parent={self.parent!r}, capability=<{len(self.capability)} bytes>)"


def _read_exactly(fd: int, size: int) -> bytes:
    chunks = []
    remaining = size
    while remaining:
        chunk = os.read(fd, remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_nested_bootstrap(fd: int = BOOTSTRAP_FD) -> NestedGrant | None:
    """Read the one frame the worker wrote, require EOF after it, and close ``fd``.

    None means this helper was not started nested-capable (``fd`` is not open). A short
    frame, trailing bytes, or a wrong magic or version refuses.
    """
    try:
        os.fstat(fd)
    except OSError:
        return None
    try:
        frame = _read_exactly(fd, _FRAME.size)
        trailing = os.read(fd, 1)
    except OSError as error:
        raise AgentTaskError(f"nested bootstrap is unreadable: {type(error).__name__}") from error
    finally:
        os.close(fd)
    if len(frame) != _FRAME.size or trailing:
        raise AgentTaskError("nested bootstrap frame has the wrong length")
    magic, version, service_epoch, record, capability = _FRAME.unpack(frame)
    if magic != BOOTSTRAP_MAGIC or version != BOOTSTRAP_VERSION:
        raise AgentTaskError("nested bootstrap frame is malformed")
    parent = (struct.unpack("<QQ", service_epoch), struct.unpack("<QQ", record))
    if parent[1] == (0, 0):
        raise AgentTaskError("nested bootstrap names no parent record")
    return NestedGrant(parent, capability)
