"""Single-file-at-a-time chunked transfer over a dedicated DataChannel.

Protocol:
  * String envelope ``{"type": "file_begin", "name", "size", "transfer_id"}``
  * Binary chunks (raw ``bytes``) follow until total bytes == size
  * String envelope ``{"type": "file_end", "transfer_id"}`` confirms

Limitations:
  * One transfer in-flight per channel (the receiver tracks a single
    active transfer; a second begin while the first is open is rejected).
  * No resume / no integrity checksum — DataChannel runs over SCTP which
    is reliable + ordered, so corruption mid-stream is not the concern.
  * No backpressure on the sender; chunks are scheduled all at once. If
    you need to ship multi-GB files, add a ``bufferedAmount`` poll.

Host inbox defaults to ``~/.je_auto_control/inbox`` and incoming filenames
are stripped of any directory components to defeat path traversal; names a
Windows filesystem would redirect (device names such as ``NUL``, a trailing
dot or space) are refused. Data goes to a ``.part`` file that replaces the
target only after exactly ``size`` bytes arrived, so a failed transfer
keeps any earlier copy.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
from pathlib import Path
from typing import Callable, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.webrtc_transport import get_bridge


_DEFAULT_CHUNK_SIZE = 16 * 1024  # 16 KB; SCTP message limit varies, 16K is safe
def default_inbox_dir() -> Path:
    """``~/.je_auto_control/inbox``, resolved at call time."""
    return Path(os.path.expanduser("~")) / ".je_auto_control" / "inbox"


class FileTransferError(AutoControlException, RuntimeError):
    """Protocol or filesystem error during a transfer."""


_MAX_SIZE = 4 * 1024 * 1024 * 1024
_WINDOWS_DEVICE_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"{prefix}{digit}" for prefix in ("COM", "LPT") for digit in range(10)])


def _safe_basename(name: str) -> str:
    if not isinstance(name, str) or not name:
        raise FileTransferError(f"invalid filename: {name!r}")
    base = Path(name).name
    if not base or base in (".", ".."):
        raise FileTransferError(f"invalid filename after sanitize: {name!r}")
    if any(ch in base for ch in "<>:\"|?*") or any(ord(ch) < 32 for ch in base):
        raise FileTransferError(f"invalid filename characters: {base!r}")
    if _redirected_on_windows(base):
        raise FileTransferError(f"filename not portable: {base!r}")
    return base


def _redirected_on_windows(base: str) -> bool:
    """Whether Windows would open something other than ``base`` itself.

    'nul' went to the null device yet was reported as received, and
    'report. ' overwrote 'report'.
    """
    return base[-1] in ". " or base.split(".")[0].upper() in _WINDOWS_DEVICE_NAMES


def _announced_size(raw) -> int:
    """Validate the envelope's ``size``: an int in 0..4 GiB."""
    try:
        size = int(raw)
    except (TypeError, ValueError, OverflowError) as error:
        raise FileTransferError(f"invalid size: {raw!r}") from error
    if size < 0 or size > _MAX_SIZE:
        raise FileTransferError(f"invalid size: {size}")
    return size


class FileTransferReceiver:
    """Reassemble incoming chunks into a file under ``inbox_dir``."""

    def __init__(self, inbox_dir: Optional[Path] = None) -> None:
        self._inbox = Path(inbox_dir) if inbox_dir else default_inbox_dir()
        self._inbox.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._current: Optional[dict] = None

    def handle_message(self, message,
                       on_progress: Optional[Callable[[int, int], None]] = None,
                       on_done: Optional[Callable[[Path], None]] = None,
                       on_error: Optional[Callable[[str], None]] = None) -> None:
        try:
            if isinstance(message, str):
                self._handle_envelope(message, on_done, on_error)
            elif isinstance(message, (bytes, bytearray, memoryview)):
                self._handle_chunk(bytes(message), on_progress)
        except FileTransferError as error:
            self._abort_locked(reason=str(error))
            if on_error is not None:
                on_error(str(error))

    def _handle_envelope(self, raw: str,
                         on_done, on_error) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as error:
            raise FileTransferError(f"bad envelope: {error}") from error
        if not isinstance(data, dict):
            raise FileTransferError("bad envelope: not an object")
        msg_type = data.get("type")
        if msg_type == "file_begin":
            self._begin(data)
        elif msg_type == "file_end":
            self._finish(on_done)
        elif msg_type == "file_abort":
            reason = "aborted by sender"
            self._abort_locked(reason=reason)
            if on_error is not None:
                on_error(reason)

    def _handle_chunk(self, chunk: bytes, on_progress) -> None:
        with self._lock:
            current = self._current
        if current is None:
            return  # silently drop stray chunk
        if current["written"] + len(chunk) > current["size"]:
            raise FileTransferError(
                f"more data than the {current['size']} bytes announced")
        try:
            current["fh"].write(chunk)
        except OSError as error:
            raise FileTransferError(f"write failed: {error}") from error
        current["written"] += len(chunk)
        if on_progress is not None:
            on_progress(current["written"], current["size"])

    def _begin(self, data: dict) -> None:
        with self._lock:
            if self._current is not None:
                raise FileTransferError("transfer already in progress")
            name = _safe_basename(data.get("name", ""))
            size = _announced_size(data.get("size", 0))
            target = self._inbox / name
            part = self._inbox / f".{name}.{secrets.token_hex(4)}.part"
            try:
                fh = part.open("wb")
            except OSError as error:
                raise FileTransferError(f"open failed: {error}") from error
            self._current = {
                "fh": fh, "size": size, "written": 0,
                "path": target, "part": part,
                "transfer_id": data.get("transfer_id", ""),
            }
        autocontrol_logger.info(
            "file transfer: receiving %s (%d bytes)", target, size,
        )

    def _finish(self, on_done) -> None:
        with self._lock:
            current = self._current
            if current is not None and current["written"] != current["size"]:
                # Raised with the transfer still current, so handle_message
                # aborts it; a truncated file used to be reported received.
                raise FileTransferError(
                    f"received {current['written']} of {current['size']} bytes")
            self._current = None
        if current is None:
            return
        try:
            current["fh"].close()
            os.replace(current["part"], current["path"])
        except OSError as error:
            current["part"].unlink(missing_ok=True)
            raise FileTransferError(f"cannot finish {current['path'].name}: {error}") from error
        autocontrol_logger.info(
            "file transfer: complete %s (%d bytes)",
            current["path"], current["written"],
        )
        if on_done is not None:
            on_done(current["path"])

    def _abort_locked(self, reason: str) -> None:
        with self._lock:
            current = self._current
            self._current = None
        if current is None:
            return
        try:
            current["fh"].close()
            current["part"].unlink(missing_ok=True)
        except OSError:
            pass
        autocontrol_logger.warning("file transfer aborted: %s", reason)


class FileTransferSender:
    """Send a single file from the caller side via the DataChannel."""

    def __init__(self, channel) -> None:
        if channel is None:
            raise ValueError("file sender requires a DataChannel")
        self._channel = channel

    def send(self, local_path,
             remote_name: Optional[str] = None,
             chunk_size: int = _DEFAULT_CHUNK_SIZE,
             on_progress: Optional[Callable[[int, int], None]] = None) -> None:
        path = Path(local_path)
        if not path.is_file():
            raise FileTransferError(f"not a file: {local_path}")
        size = path.stat().st_size
        name = _safe_basename(remote_name or path.name)
        transfer_id = secrets.token_hex(8)
        bridge = get_bridge()
        bridge.call_soon(self._channel.send, json.dumps({
            "type": "file_begin", "name": name,
            "size": size, "transfer_id": transfer_id,
        }))
        sent = 0
        try:
            with path.open("rb") as fh:
                while True:
                    chunk = fh.read(chunk_size)
                    if not chunk:
                        break
                    bridge.call_soon(self._channel.send, chunk)
                    sent += len(chunk)
                    if on_progress is not None:
                        on_progress(sent, size)
        except OSError as error:
            bridge.call_soon(self._channel.send, json.dumps({
                "type": "file_abort", "transfer_id": transfer_id,
            }))
            raise FileTransferError(f"read failed: {error}") from error
        bridge.call_soon(self._channel.send, json.dumps({
            "type": "file_end", "transfer_id": transfer_id,
        }))


__all__ = [
    "FileTransferError", "FileTransferReceiver", "FileTransferSender",
]
