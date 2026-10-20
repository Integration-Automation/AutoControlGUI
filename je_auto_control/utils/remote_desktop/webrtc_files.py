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
  * Sender calls observe channel acceptance, not a remote commit acknowledgement.
    Writes are bounded/cancellable and pause above one MiB of buffered data.

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

from je_auto_control.utils.exception.control_signals import raise_caused_run_interruption
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.webrtc_transport import get_bridge
from je_auto_control.utils.remote_desktop.webrtc_file_write import (
    _PinnedBridge, _channel_transfer, _checkpoint, _send_confirmed,
)


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
        self._closed = False

    def abort(self, reason: str = 'receive permission ended') -> None:
        """Discard the active partial file while keeping this receiver available for a later allowed transfer."""
        self._abort_locked(reason)

    def close(self) -> None:
        """Permanently refuse further frames and discard any partial file; safe to repeat or race with a write."""
        with self._lock:
            self._closed = True
        self._abort_locked('receiver closed')

    def handle_message(self, message,
                       on_progress: Optional[Callable[[int, int], None]] = None,
                       on_done: Optional[Callable[[Path], None]] = None,
                       on_error: Optional[Callable[[str], None]] = None) -> None:
        """Consume one envelope or chunk; publish complete files before notifying completion."""
        with self._lock:
            if self._closed:
                return
        try:
            if isinstance(message, str):
                self._handle_envelope(message, on_done, on_error)
            elif isinstance(message, (bytes, bytearray, memoryview)):
                self._handle_chunk(bytes(message), on_progress)
        except FileTransferError as error:
            try:
                self._abort_locked(reason=str(error))
            finally:
                raise_caused_run_interruption(error)
            if on_error is not None:
                on_error(str(error))
        except BaseException as error:  # reason: clean partial bytes before propagating callback or write signals
            try:
                self._abort_locked(reason='receive callback failed')
            finally:
                raise_caused_run_interruption(error)
            raise

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
            if self._closed or current is None:
                return  # silently drop stray or closed-owner chunks
            if current["written"] + len(chunk) > current["size"]:
                raise FileTransferError(
                    f"more data than the {current['size']} bytes announced")
            try:
                current["fh"].write(chunk)
            except OSError as error:
                raise FileTransferError(f"write failed: {error}") from error
            current["written"] += len(chunk)
            written, size = current['written'], current['size']
        if on_progress is not None:
            on_progress(written, size)

    def _begin(self, data: dict) -> None:
        with self._lock:
            if self._closed:
                return
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
            if self._closed or current is None:
                return
            if current["written"] != current["size"]:
                # Raised with the transfer still current, so handle_message
                # aborts it; a truncated file used to be reported received.
                raise FileTransferError(
                    f"received {current['written']} of {current['size']} bytes")
            try:
                current["fh"].close()
                os.replace(current["part"], current["path"])
            except OSError as error:
                raise FileTransferError(f"cannot finish {current['path'].name}: {error}") from error
            self._current = None
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
            _discard_partial(current)
        autocontrol_logger.warning("file transfer aborted: %s", reason)


def _discard_partial(current: dict) -> None:
    """Attempt both cleanup operations before preserving the first original interruption."""
    failures = []
    for operation in (current['fh'].close, lambda: current['part'].unlink(missing_ok=True)):
        try:
            operation()
        # pylint: disable-next=broad-exception-caught  # reason: finish both cleanup operations before selecting a signal
        except BaseException as error:  # reason: defer cleanup signals until unlink has also been attempted
            failures.append(error)
    for failure in failures:
        raise_caused_run_interruption(failure)
        autocontrol_logger.warning('file receive cleanup failed: %r', failure)


class FileTransferSender:
    """Send a single file from the caller side via the DataChannel."""

    def __init__(self, channel) -> None:
        if channel is None:
            raise ValueError("file sender requires a DataChannel")
        self._channel = channel

    def send(self, local_path,
             remote_name: Optional[str] = None,
             chunk_size: int = _DEFAULT_CHUNK_SIZE,
             on_progress: Optional[Callable[[int, int], None]] = None, *,
             cancelled: Optional[Callable[[], bool]] = None) -> None:
        """Return only after channel writes execute; cancellation aborts partial files without remote commit claims."""
        try:
            _checkpoint(cancelled)
            if getattr(self._channel, 'readyState', 'open') != 'open':
                raise FileTransferError('files channel is not open')
            if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or not 1 <= chunk_size <= 1024 * 1024:
                raise FileTransferError('chunk size must be an integer from 1 through 1048576')
            path = Path(local_path)
            if not path.is_file():
                raise FileTransferError(f'not a file: {local_path}')
            size = path.stat().st_size
            if size > _MAX_SIZE:
                raise FileTransferError('file exceeds the four-GiB protocol limit')
            name = _safe_basename(remote_name or path.name)
            with _channel_transfer(self._channel):
                self._transfer(path, name, size, chunk_size, on_progress, cancelled)
        except FileTransferError as error:
            raise_caused_run_interruption(error)
            raise
        except BaseException as error:  # reason: preserve signals while containing ordinary channel failures
            raise _send_failure(error) from error

    def _transfer(self, path, name, size, chunk_size, on_progress, cancelled) -> None:
        transfer_id = secrets.token_hex(8)
        bridge = _PinnedBridge(get_bridge())
        try:
            _send_confirmed(self._channel, bridge, json.dumps({
                'type': 'file_begin', 'name': name, 'size': size, 'transfer_id': transfer_id}), cancelled=cancelled)
            self._chunks(path, size, chunk_size, on_progress, bridge, cancelled)
            _send_confirmed(self._channel, bridge, json.dumps({
                'type': 'file_end', 'transfer_id': transfer_id}), cancelled=cancelled)
        except BaseException as error:  # reason: abort partial transfers before propagating their failure
            cleanup_error = None
            try:
                _send_confirmed(self._channel, bridge, json.dumps({
                    'type': 'file_abort', 'transfer_id': transfer_id}), timeout=1.0, retain_abort=True)
            # pylint: disable-next=broad-exception-caught  # reason: preserve the original signal before cleanup signals
            except BaseException as secondary:  # reason: select the original interruption before a cleanup interruption
                cleanup_error = secondary
            converted = _send_failure(error, cleanup_error)
            if converted is error:
                raise
            raise converted from error

    def _chunks(self, path, size, chunk_size, on_progress, bridge, cancelled) -> None:
        sent = 0
        try:
            _checkpoint(cancelled)
            bridge.validate()
            with path.open('rb') as stream:
                while True:
                    _checkpoint(cancelled)
                    bridge.validate()
                    chunk = stream.read(chunk_size)
                    if not chunk:
                        if sent != size:
                            raise FileTransferError('source size changed during transfer')
                        return
                    if sent + len(chunk) > size:
                        raise FileTransferError('source size changed during transfer')
                    _send_confirmed(self._channel, bridge, chunk, cancelled=cancelled)
                    sent += len(chunk)
                    if on_progress is not None:
                        on_progress(sent, size)
        except OSError as error:
            raise_caused_run_interruption(error)
            raise FileTransferError(f'read failed: {error}') from error


def _send_failure(error: BaseException, cleanup: Optional[BaseException] = None) -> FileTransferError:
    raise_caused_run_interruption(error)
    if cleanup is not None:
        raise_caused_run_interruption(cleanup)
    if isinstance(error, FileTransferError):
        return error
    converted = FileTransferError('file send failed before complete channel acceptance')
    converted.__cause__ = error
    return converted


__all__ = [
    "FileTransferError", "FileTransferReceiver", "FileTransferSender",
]
