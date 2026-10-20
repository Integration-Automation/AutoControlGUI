"""Single-file-at-a-time chunked transfer over a dedicated DataChannel.

Protocol:
  * String envelope ``{"type": "file_begin", "name", "size", "transfer_id"}``
  * Binary chunks (raw ``bytes``) follow until total bytes == size
  * String envelope ``{"type": "file_end", "transfer_id"}`` ends the legacy stream.
  * Native confirmed sends probe support, use ``commit: 2`` and bind end SHA-256/nonce
    to an authenticated ``file_commit`` response after atomic publication.

Limitations:
  * One transfer in-flight per channel (the receiver tracks a single
    active transfer; a second begin while the first is open is rejected).
  * No resume. Legacy manual sends confirm channel acceptance without a peer checksum/receipt.
  * ``require_commit=True`` needs a native listener and a compatible authenticated peer;
    source reads follow a bounded probe and success waits for matching publication metadata.
  * Writes are bounded/cancellable and pause above one MiB of buffered data.

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
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Callable, Optional

from je_auto_control.utils.exception.control_signals import raise_caused_run_interruption
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.file_receipts import FileReceiveReceipt
from je_auto_control.utils.remote_desktop.webrtc_file_commit import (
    ConfirmedPeer, FileCommitError, commit_request, confirmed_peer, valid_hex, valid_int,
)
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


def _confirmed_begin(data: dict) -> bool:
    version = data.get('commit')
    if version is None:
        return False
    if not valid_int(version) or version != 2 or not valid_hex(data.get('transfer_id'), 16):
        raise FileTransferError('invalid publication-confirmed file begin')
    if not valid_int(data.get('size')):
        raise FileTransferError('confirmed file size must be an integer')
    return True


def _confirmed_end(current: dict, data: dict) -> None:
    if not current['commit']:
        return
    if (data.get('transfer_id') != current['transfer_id'] or not valid_hex(data.get('sha256'), 64)
            or not valid_hex(data.get('commit_nonce'), 32)):
        raise FileTransferError('invalid publication-confirmed file end')
    if data['sha256'] != current['digest'].hexdigest():
        raise FileTransferError('received file checksum does not match sender')


class FileTransferReceiver:
    """Reassemble incoming chunks into a file under ``inbox_dir``."""

    def __init__(self, inbox_dir: Optional[Path] = None) -> None:
        self._inbox = (Path(inbox_dir) if inbox_dir else default_inbox_dir()).absolute()
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
                       on_error: Optional[Callable[[str], None]] = None, *,
                       on_receipt: Optional[Callable[[FileReceiveReceipt], None]] = None) -> None:
        """Consume one envelope or chunk; publish complete files before notifying completion."""
        with self._lock:
            if self._closed:
                return
        try:
            if isinstance(message, str):
                self._handle_envelope(message, on_done, on_error, on_receipt)
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
                         on_done, on_error, on_receipt) -> None:
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
            self._finish(on_done, on_receipt, data)
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
                written = current["fh"].write(chunk)
            except OSError as error:
                raise FileTransferError(f"write failed: {error}") from error
            if written != len(chunk):
                raise FileTransferError('incomplete file chunk write')
            current['digest'].update(chunk)
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
            commit = _confirmed_begin(data)
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
                "digest": sha256(),
                "commit": commit,
            }
        autocontrol_logger.info(
            "file transfer: receiving %s (%d bytes)", target, size,
        )

    def _finish(self, on_done, on_receipt, data) -> None:
        with self._lock:
            current = self._current
            if self._closed or current is None:
                return
            if current["written"] != current["size"]:
                # Raised with the transfer still current, so handle_message
                # aborts it; a truncated file used to be reported received.
                raise FileTransferError(
                    f"received {current['written']} of {current['size']} bytes")
            _confirmed_end(current, data)
            try:
                current["fh"].close()
                os.replace(current["part"], current["path"])
            except OSError as error:
                raise FileTransferError(f"cannot finish {current['path'].name}: {error}") from error
            self._current = None
            receipt = FileReceiveReceipt(current['path'], current['digest'].hexdigest(), current['written'])
        autocontrol_logger.info(
            "file transfer: complete %s (%d bytes)",
            current["path"], current["written"],
        )
        if on_receipt is not None:
            on_receipt(receipt)
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


@dataclass(frozen=True)
class _SendPlan:
    """Capture source metadata and the original confirmation owner for one file send."""
    path: Path
    name: str
    size: int
    chunk_size: int
    peer: Optional[ConfirmedPeer] = None
    transfer_id: str = field(default_factory=lambda: secrets.token_hex(8))


def _send_options(channel: object, chunk_size: int, require_commit: bool) -> None:
    if getattr(channel, 'readyState', 'open') != 'open':
        raise FileTransferError('files channel is not open')
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or not 1 <= chunk_size <= 1024 * 1024:
        raise FileTransferError('chunk size must be an integer from 1 through 1048576')
    if not isinstance(require_commit, bool):
        raise FileTransferError('require_commit must be a boolean')


def _source_plan(local_path, remote_name, chunk_size, peer) -> _SendPlan:
    path = Path(local_path)
    if not path.is_file():
        raise FileTransferError(f'not a file: {local_path}')
    size = path.stat().st_size
    if size > _MAX_SIZE:
        raise FileTransferError('file exceeds the four-GiB protocol limit')
    return _SendPlan(path, _safe_basename(remote_name or path.name), size, chunk_size, peer)


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
             cancelled: Optional[Callable[[], bool]] = None, require_commit: bool = False) -> None:
        """Confirm queued writes, or require a native peer's matching atomic-publication receipt when requested."""
        try:
            _checkpoint(cancelled)
            _send_options(self._channel, chunk_size, require_commit)
            source_path = Path(local_path).absolute()
            with _channel_transfer(self._channel):
                bridge = _PinnedBridge(get_bridge()) if require_commit else None
                peer = confirmed_peer(self._channel, bridge, cancelled) if bridge is not None else None
                plan = _source_plan(source_path, remote_name, chunk_size, peer)
                self._transfer(plan, on_progress, bridge or _PinnedBridge(get_bridge()), cancelled)
        except FileTransferError as error:
            raise_caused_run_interruption(error)
            raise
        except BaseException as error:  # reason: preserve signals while containing ordinary channel failures
            raise _send_failure(error, require_commit=require_commit) from error

    def _transfer(self, plan, on_progress, bridge, cancelled) -> None:
        guard = plan.peer.guard if plan.peer is not None else cancelled
        try:
            with commit_request(plan.peer, plan.transfer_id, plan.size) as request:
                begin = {'type': 'file_begin', 'name': plan.name, 'size': plan.size, 'transfer_id': plan.transfer_id}
                if request is not None:
                    begin['commit'] = 2
                _send_confirmed(self._channel, bridge, json.dumps(begin), cancelled=guard)
                digest = self._chunks(plan, on_progress, bridge, guard)
                end = {'type': 'file_end', 'transfer_id': plan.transfer_id}
                if request is not None:
                    end.update(request.end_fields(digest))
                _send_confirmed(self._channel, bridge, json.dumps(end), cancelled=guard)
                if request is not None:
                    request.wait()
        except BaseException as error:  # reason: abort partial transfers before propagating their failure
            cleanup_error = None
            try:
                _send_confirmed(self._channel, bridge, json.dumps({
                    'type': 'file_abort', 'transfer_id': plan.transfer_id}), timeout=1.0, retain_abort=True)
            # pylint: disable-next=broad-exception-caught  # reason: preserve the original signal before cleanup signals
            except BaseException as secondary:  # reason: select the original interruption before a cleanup interruption
                cleanup_error = secondary
            converted = _send_failure(error, cleanup_error, require_commit=plan.peer is not None)
            if converted is error:
                raise
            raise converted from error

    def _chunks(self, plan, on_progress, bridge, cancelled) -> str:
        sent = 0
        digest = sha256()
        try:
            _checkpoint(cancelled)
            bridge.validate()
            with plan.path.open('rb') as stream:
                while True:
                    _checkpoint(cancelled)
                    bridge.validate()
                    chunk = stream.read(plan.chunk_size)
                    if not chunk:
                        if sent != plan.size:
                            raise FileTransferError('source size changed during transfer')
                        return digest.hexdigest()
                    if sent + len(chunk) > plan.size:
                        raise FileTransferError('source size changed during transfer')
                    _send_confirmed(self._channel, bridge, chunk, cancelled=cancelled)
                    digest.update(chunk)
                    sent += len(chunk)
                    if on_progress is not None:
                        on_progress(sent, plan.size)
        except OSError as error:
            raise_caused_run_interruption(error)
            raise FileTransferError(f'read failed: {error}') from error


def _send_failure(error: BaseException, cleanup: Optional[BaseException] = None, *,
                  require_commit: bool = False) -> FileTransferError:
    raise_caused_run_interruption(error)
    if cleanup is not None:
        raise_caused_run_interruption(cleanup)
    if isinstance(error, FileTransferError):
        return error
    message = 'file send failed before complete channel acceptance'
    if require_commit:
        message = 'file send failed before publication confirmation'
        if isinstance(error, FileCommitError):
            message = str(error)
    converted = FileTransferError(message)
    converted.__cause__ = error
    return converted


__all__ = [
    "FileTransferError", "FileTransferReceiver", "FileTransferSender",
]
