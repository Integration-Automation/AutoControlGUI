"""Chunked file transfer over the typed-message channel.

Three message types form a transfer:

* ``FILE_BEGIN`` — JSON ``{transfer_id, dest_path, size}`` announces a new
  stream. ``transfer_id`` is a 36-character UUID hex string so the
  receiver can demultiplex multiple in-flight transfers on one channel.
* ``FILE_CHUNK`` — first 36 bytes are the ASCII transfer id, the rest is
  raw payload. Chunks arrive in order; the receiver writes them
  sequentially and accumulates ``bytes_done``.
* ``FILE_END`` — JSON ``{transfer_id, status, error?}`` finalises the
  stream. The receiver closes the file and fires ``on_complete`` with
  success / failure info.

There is no central per-host file-size limit — operators relying on
this should keep ``trusted token holders == trusted users`` in mind, and
treat the dropbox / destination filesystem accordingly.

The receiver writes to a ``.part`` file beside the destination and renames
it into place only when ``FILE_END`` reports success and exactly the
announced number of bytes arrived, so a failed transfer never truncates an
existing file or leaves a partial one behind.
"""
import json
import os
import threading
from collections import OrderedDict
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.remote_desktop.protocol import MessageType

DEFAULT_CHUNK_SIZE = 256 * 1024
TRANSFER_ID_LEN = 36  # str(uuid.uuid4()) length

_INVALID_TRANSFER_ID_MESSAGE = (
    f"transfer_id must be a {TRANSFER_ID_LEN}-char UUID string"
)

ProgressCallback = Callable[[str, int, int], None]
CompleteCallback = Callable[[str, bool, Optional[str], str], None]


class FileTransferError(AutoControlException, RuntimeError):
    """Raised when a file-transfer payload is malformed."""


def new_transfer_id() -> str:
    """Return a fresh 36-character ASCII transfer ID."""
    return str(uuid.uuid4())


def encode_begin(transfer_id: str, dest_path: str, size: int) -> bytes:
    if len(transfer_id) != TRANSFER_ID_LEN:
        raise FileTransferError(_INVALID_TRANSFER_ID_MESSAGE)
    return json.dumps({
        "transfer_id": transfer_id,
        "dest_path": str(dest_path),
        "size": int(size),
    }, ensure_ascii=False).encode("utf-8")


def decode_begin(payload: bytes) -> Tuple[str, str, int]:
    body = _decode_json(payload)
    transfer_id = body.get("transfer_id")
    dest_path = body.get("dest_path")
    size = body.get("size")
    if (not isinstance(transfer_id, str)
            or len(transfer_id) != TRANSFER_ID_LEN):
        raise FileTransferError("FILE_BEGIN missing valid transfer_id")
    if not isinstance(dest_path, str) or not dest_path:
        raise FileTransferError("FILE_BEGIN missing dest_path")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise FileTransferError("FILE_BEGIN missing valid size")
    return transfer_id, dest_path, size


def encode_chunk(transfer_id: str, chunk: bytes) -> bytes:
    if len(transfer_id) != TRANSFER_ID_LEN:
        raise FileTransferError(_INVALID_TRANSFER_ID_MESSAGE)
    return transfer_id.encode("ascii") + bytes(chunk)


def decode_chunk(payload: bytes) -> Tuple[str, bytes]:
    if len(payload) < TRANSFER_ID_LEN:
        raise FileTransferError("FILE_CHUNK shorter than transfer id header")
    transfer_id = payload[:TRANSFER_ID_LEN].decode("ascii", errors="replace")
    return transfer_id, bytes(payload[TRANSFER_ID_LEN:])


def encode_end(transfer_id: str, status: str = "ok",
               error: Optional[str] = None) -> bytes:
    if len(transfer_id) != TRANSFER_ID_LEN:
        raise FileTransferError(_INVALID_TRANSFER_ID_MESSAGE)
    body: Dict[str, Any] = {"transfer_id": transfer_id, "status": status}
    if error is not None:
        body["error"] = str(error)
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


def decode_end(payload: bytes) -> Tuple[str, str, Optional[str]]:
    body = _decode_json(payload)
    transfer_id = body.get("transfer_id")
    status = body.get("status", "ok")
    if (not isinstance(transfer_id, str)
            or len(transfer_id) != TRANSFER_ID_LEN):
        raise FileTransferError("FILE_END missing valid transfer_id")
    if not isinstance(status, str):
        raise FileTransferError("FILE_END status must be a string")
    error = body.get("error")
    return transfer_id, status, error if isinstance(error, str) else None


def _decode_json(payload: bytes) -> Dict[str, Any]:
    try:
        body = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FileTransferError(f"invalid JSON: {error}") from error
    if not isinstance(body, dict):
        raise FileTransferError("payload must be a JSON object")
    return body


@dataclass
class _Incoming:
    """Per-transfer state owned by ``FileReceiver``."""

    transfer_id: str
    dest_path: Path
    part_path: Path
    total_size: int
    handle: Any  # file object
    bytes_done: int = 0
    error: Optional[str] = None


def _discard(part: Path) -> None:
    """Delete a part file that will not be renamed into place."""
    try:
        part.unlink(missing_ok=True)
    except OSError as error:
        autocontrol_logger.info("remote_desktop part file %s left: %r", part, error)


#: How many aborted-before-they-began transfer ids a receiver remembers.
_CANCELLED_MAX = 1024


class FileReceiver:
    """Demultiplex incoming FILE_* messages into one or more file writes."""

    def __init__(self, on_progress: Optional[ProgressCallback] = None,
                 on_complete: Optional[CompleteCallback] = None) -> None:
        self._on_progress = on_progress
        self._on_complete = on_complete
        self._active: Dict[str, _Incoming] = {}
        # Transfers aborted before FILE_BEGIN registered them. A viewer that
        # disconnected while its begin was opening the part file had the
        # abort miss (nothing registered yet), and the part file and its open
        # handle were left behind for good.
        self._cancelled: "OrderedDict[str, bool]" = OrderedDict()
        self._lock = threading.Lock()

    def handle_begin(self, payload: bytes) -> None:
        transfer_id, dest_path, total_size = decode_begin(payload)
        with self._lock:
            duplicate = transfer_id in self._active
            cancelled = self._cancelled.pop(transfer_id, False)
        if duplicate:
            # Replacing the entry leaked the first transfer's open handle.
            autocontrol_logger.info(
                "remote_desktop FILE_BEGIN for active transfer %s ignored",
                transfer_id,
            )
            return
        if cancelled:
            self._fire_complete(transfer_id, False, "cancelled before it began", str(dest_path))
            return
        path = Path(os.path.expanduser(dest_path))
        if not path.name:   # ".", "/" or "C:\\": with_name raised ValueError past the handler
            self._fire_complete(transfer_id, False, "dest_path names no file", str(path))
            return
        part = path.with_name(f".{path.name}.{transfer_id[:8]}.part")
        try:
            # mkdir inside the try: a NUL in the name (ValueError) or a
            # protected directory killed the connection's receive thread.
            path.parent.mkdir(parents=True, exist_ok=True)
            handle = open(part, "wb")  # noqa: SIM115  managed manually
        except (OSError, ValueError) as error:
            self._fire_complete(transfer_id, False, str(error), str(path))
            return
        incoming = _Incoming(transfer_id=transfer_id, dest_path=path, part_path=part,
                             total_size=total_size, handle=handle)
        if not self._register(incoming):
            incoming.error = "cancelled before it began"
            self._abort(incoming)
            return
        if self._on_progress is not None:
            self._on_progress(transfer_id, 0, total_size)

    def _register(self, incoming: _Incoming) -> bool:
        """Make ``incoming`` active, unless it was aborted while its file opened."""
        with self._lock:
            if self._cancelled.pop(incoming.transfer_id, False):
                return False
            self._active[incoming.transfer_id] = incoming
            return True

    def handle_chunk(self, payload: bytes) -> None:
        transfer_id, chunk = decode_chunk(payload)
        with self._lock:
            incoming = self._active.get(transfer_id)
        if incoming is None:
            autocontrol_logger.info(
                "remote_desktop FILE_CHUNK for unknown transfer %s",
                transfer_id,
            )
            return
        if incoming.bytes_done + len(chunk) > incoming.total_size:
            incoming.error = (
                f"more data than the {incoming.total_size} bytes announced")
            self._abort(incoming)
            return
        try:
            incoming.handle.write(chunk)
        except OSError as error:
            incoming.error = str(error)
            self._abort(incoming)
            return
        incoming.bytes_done += len(chunk)
        if self._on_progress is not None:
            self._on_progress(
                transfer_id, incoming.bytes_done, incoming.total_size,
            )

    def handle_end(self, payload: bytes) -> None:
        transfer_id, status, error = decode_end(payload)
        with self._lock:
            incoming = self._active.pop(transfer_id, None)
        if incoming is None:
            return
        ok, message = self._commit(incoming, status == "ok", error)
        self._fire_complete(
            transfer_id, ok, message, str(incoming.dest_path),
        )

    @staticmethod
    def _commit(incoming: _Incoming, sender_ok: bool,
                sender_error: Optional[str]) -> Tuple[bool, Optional[str]]:
        """Close the part file and rename it into place, or discard it."""
        message = sender_error or incoming.error
        try:
            incoming.handle.close()
        except OSError as close_error:
            message = message or str(close_error)
        ok = sender_ok and message is None
        if ok and incoming.bytes_done != incoming.total_size:
            ok, message = False, (
                f"received {incoming.bytes_done} of {incoming.total_size} bytes")
        if ok:
            try:
                os.replace(incoming.part_path, incoming.dest_path)
                return True, None
            except OSError as replace_error:
                ok, message = False, str(replace_error)
        _discard(incoming.part_path)
        return ok, message

    def abort(self, transfer_id: str, reason: str) -> None:
        """Abandon an in-flight transfer: close it and delete its part file."""
        with self._lock:
            incoming = self._active.get(transfer_id)
            if incoming is None:
                # Not begun yet (or already finished): remembered, so a
                # FILE_BEGIN still on its way does not open a part file
                # nobody will abort.
                self._cancelled[transfer_id] = True
                while len(self._cancelled) > _CANCELLED_MAX:
                    self._cancelled.popitem(last=False)
                return
        incoming.error = incoming.error or reason
        self._abort(incoming)

    def abort_all(self, reason: str) -> None:
        """Abandon every in-flight transfer (the host is stopping)."""
        with self._lock:
            transfer_ids = list(self._active)
        for transfer_id in transfer_ids:
            self.abort(transfer_id, reason)

    def _abort(self, incoming: _Incoming) -> None:
        try:
            incoming.handle.close()
        except OSError:
            pass
        _discard(incoming.part_path)
        with self._lock:
            self._active.pop(incoming.transfer_id, None)
        self._fire_complete(
            incoming.transfer_id, False, incoming.error,
            str(incoming.dest_path),
        )

    def _fire_complete(self, transfer_id: str, ok: bool,
                       error: Optional[str], dest_path: str) -> None:
        if self._on_complete is None:
            return
        try:
            self._on_complete(transfer_id, ok, error, dest_path)
        except Exception:  # noqa: BLE001  # reason: callback isolation, a caller's handler must not kill the receive loop
            autocontrol_logger.exception(
                "remote_desktop FileReceiver.on_complete callback raised"
            )


@dataclass
class FileSendResult:
    """Outcome of one outbound transfer."""

    transfer_id: str
    success: bool
    error: Optional[str] = None
    bytes_sent: int = 0


def send_file(channel, source_path: str, dest_path: str,
              on_progress: Optional[ProgressCallback] = None,
              chunk_size: int = DEFAULT_CHUNK_SIZE,
              transfer_id: Optional[str] = None) -> FileSendResult:
    """Stream ``source_path`` to ``dest_path`` over ``channel``.

    Synchronous: the caller's thread does the I/O. Wrap in a thread for
    background uploads. ``on_progress(transfer_id, bytes_done, total)``
    fires after every chunk (and once at the start with ``bytes_done=0``).
    """
    transfer_id = transfer_id or new_transfer_id()
    source = Path(os.path.expanduser(source_path))
    if not source.is_file():
        raise FileTransferError(f"source not found: {source}")
    total_size = source.stat().st_size
    channel.send_typed(MessageType.FILE_BEGIN,
                       encode_begin(transfer_id, dest_path, total_size))
    if on_progress is not None:
        on_progress(transfer_id, 0, total_size)
    bytes_sent = 0
    try:
        with open(source, "rb") as handle:
            while True:
                chunk = handle.read(int(chunk_size))
                if not chunk:
                    break
                channel.send_typed(
                    MessageType.FILE_CHUNK, encode_chunk(transfer_id, chunk),
                )
                bytes_sent += len(chunk)
                if on_progress is not None:
                    on_progress(transfer_id, bytes_sent, total_size)
    except OSError as error:
        channel.send_typed(
            MessageType.FILE_END,
            encode_end(transfer_id, status="error", error=str(error)),
        )
        return FileSendResult(transfer_id=transfer_id, success=False,
                              error=str(error), bytes_sent=bytes_sent)
    channel.send_typed(MessageType.FILE_END, encode_end(transfer_id))
    return FileSendResult(transfer_id=transfer_id, success=True,
                          bytes_sent=bytes_sent)
