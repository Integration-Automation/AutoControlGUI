"""Read/write a JSON object to a file, tolerating a missing/corrupt file.

Several stores (asset store, approval gate, …) persist a single JSON dict to
disk with identical boilerplate; this centralises it so they don't duplicate the
load/flush logic. Pure standard library; imports no ``PySide6``.
"""
import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Optional, TypeVar, Union

from je_auto_control.utils.logging.logging_instance import autocontrol_logger

_Result = TypeVar("_Result")


def atomic_write_text(path: Union[str, Path], text: str,
                      encoding: str = "utf-8") -> None:
    """Atomically write ``text`` to ``path`` via a sibling temp file + rename.

    The new bytes land in a temp file in the same directory and only replace
    the destination once fully written, so a crash mid-write leaves the
    previous file intact instead of truncating it. Leftover temp files are
    removed on failure.
    """
    _atomic_write(path, lambda handle_fd: _write_text_fd(handle_fd, text, encoding))


def atomic_write_bytes(path: Union[str, Path], data: bytes) -> None:
    """Atomically write ``data`` to ``path``, byte for byte.

    Like :func:`atomic_write_text` -- same temp file, same rename, and on
    POSIX the file is 0600 from the moment it exists -- without newline
    translation, for content such as a PEM private key.
    """
    def write(handle_fd: int) -> None:
        with os.fdopen(handle_fd, "wb") as handle:
            handle.write(data)
    _atomic_write(path, write)


def _write_text_fd(handle_fd: int, text: str, encoding: str) -> None:
    with os.fdopen(handle_fd, "w", encoding=encoding) as handle:
        handle.write(text)


def _atomic_write(path: Union[str, Path], write: Callable[[int], None]) -> None:
    file_path = Path(path)
    directory = str(file_path.parent) or "."
    handle_fd, tmp_name = tempfile.mkstemp(
        dir=directory, prefix=f".{file_path.name}.", suffix=".tmp")
    try:
        write(handle_fd)
        os.replace(tmp_name, str(file_path))
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def append_json_line(path: Union[str, Path], line: str) -> None:
    """Append ``line`` and a newline to a JSON-lines file.

    If the file does not end in a newline -- the last write was cut off --
    one is written first. Otherwise the new record joined the torn line and
    was unreadable along with it.
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("ab+") as handle:  # appends always land at the end
        if handle.seek(0, os.SEEK_END) > 0:
            handle.seek(-1, os.SEEK_END)
            if handle.read(1) != b"\n":
                handle.write(b"\n")
        handle.write(line.encode("utf-8") + b"\n")


def read_json_dict(path: Optional[Union[str, Path]]) -> Dict[str, Any]:
    """Return the JSON object at ``path``, or ``{}`` if missing/unreadable."""
    if path is None:
        return {}
    file_path = Path(path)
    if not file_path.is_file():
        return {}
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _read_json_object(path: Path) -> Dict[str, Any]:
    """The JSON object at ``path`` (``{}`` if missing); anything else raises ``ValueError``."""
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not hold a JSON object")
    return data


def write_json_dict(path: Union[str, Path], data: Dict[str, Any]) -> None:
    """Write ``data`` as indented JSON to ``path`` (creating parent dirs)."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        file_path, json.dumps(data, ensure_ascii=False, indent=2))


_LOCK_WAIT_S = 10.0
_LOCK_STALE_S = 30.0


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    """Hold ``<path>.lock`` for the duration; several processes may contend.

    Created with ``O_CREAT | O_EXCL``, which is atomic on every platform. A
    lock older than ``_LOCK_STALE_S`` was left by a process that died holding
    it and is taken over; waiting longer than ``_LOCK_WAIT_S`` raises
    ``TimeoutError``.
    """
    lock = path.with_name(path.name + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + _LOCK_WAIT_S
    while True:
        try:
            os.close(os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
            break
        # Windows reports a lock file that is being deleted as PermissionError.
        except (FileExistsError, PermissionError):
            if _lock_is_stale(lock):
                lock.unlink(missing_ok=True)
                continue
            if time.monotonic() > deadline:
                raise TimeoutError(f"{lock} is held by another process") from None
            time.sleep(0.01)
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def _lock_is_stale(lock: Path) -> bool:
    try:
        return time.time() - lock.stat().st_mtime > _LOCK_STALE_S
    except OSError:
        return False  # released (or being released) meanwhile; try again


class SharedJsonDict:
    """A JSON-object file that several processes read and update.

    Each :meth:`update` takes a lock file, re-reads the file, applies the
    change and writes it back atomically, and each :meth:`read` reads the
    file afresh. Stores that loaded the file once and wrote back their own
    copy on every change lost each other's updates -- two checkers deciding
    one approval request were both told they had succeeded. With no path the
    dict lives in memory only.

    By default an unreadable file reads as empty. With ``strict`` it raises
    ``ValueError`` instead -- for stores of user-authored content (skills,
    locators) where writing back an empty dict would erase the file.
    """

    def __init__(self, path: Optional[Union[str, Path]], *,
                 strict: bool = False) -> None:
        self._path = Path(path) if path is not None else None
        self._memory: Dict[str, Any] = {}
        self._strict = strict

    def _load(self, path: Path) -> Dict[str, Any]:
        return _read_json_object(path) if self._strict else read_json_dict(path)

    def read(self) -> Dict[str, Any]:
        """Return the current contents (a fresh copy when file-backed)."""
        if self._path is None:
            return self._memory
        return self._load(self._path)

    def update(self, mutate: Callable[[Dict[str, Any]], _Result]) -> _Result:
        """Apply ``mutate`` to the current contents and persist them."""
        if self._path is None:
            return mutate(self._memory)
        with _file_lock(self._path):
            data = self._load(self._path)
            result = mutate(data)
            write_json_dict(self._path, data)
        return result


def quarantine_file(path: Union[str, Path], label: str, reason: Any) -> Optional[Path]:
    """Move an unusable store file aside as ``<name>.corrupt-<time>``; return where.

    A store that reads a damaged file as empty and then saves replaces every
    entry the file held. Moving it aside keeps the data for the operator and
    lets the store start clean. Returns ``None`` when the move fails.
    """
    source = Path(path)
    target = source.with_name(f"{source.name}.corrupt-{int(time.time())}")
    try:
        os.replace(source, target)
    except OSError as error:
        autocontrol_logger.error("%s %s unreadable (%s) and could not be moved aside: %r",
                                 label, source, reason, error)
        return None
    autocontrol_logger.warning("%s %s unreadable (%s); moved to %s", label, source, reason, target)
    return target


def load_json_or_quarantine(path: Union[str, Path], label: str) -> Any:
    """The JSON at ``path``, ``None`` when missing; damaged content is quarantined.

    See :func:`quarantine_file`. A UTF-8 BOM is accepted. Only content that
    is not UTF-8 JSON is moved aside: an ``OSError`` reading the file (a lock
    held by an antivirus scan, a permission error) says nothing about what
    it holds, and moving a good file aside started the store empty -- for
    known_hosts that reset every pinned fingerprint. Such errors propagate.
    """
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return None
    except UnicodeDecodeError as error:
        quarantine_file(source, label, repr(error))
        return None
    try:
        return json.loads(text)
    except ValueError as error:
        quarantine_file(source, label, repr(error))
        return None

