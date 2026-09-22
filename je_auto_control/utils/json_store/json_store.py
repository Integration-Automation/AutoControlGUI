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

_Result = TypeVar("_Result")


def atomic_write_text(path: Union[str, Path], text: str,
                      encoding: str = "utf-8") -> None:
    """Atomically write ``text`` to ``path`` via a sibling temp file + rename.

    The new bytes land in a temp file in the same directory and only replace
    the destination once fully written, so a crash mid-write leaves the
    previous file intact instead of truncating it. Leftover temp files are
    removed on failure.
    """
    file_path = Path(path)
    directory = str(file_path.parent) or "."
    handle_fd, tmp_name = tempfile.mkstemp(
        dir=directory, prefix=f".{file_path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle_fd, "w", encoding=encoding) as handle:
            handle.write(text)
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
    """

    def __init__(self, path: Optional[Union[str, Path]]) -> None:
        self._path = Path(path) if path is not None else None
        self._memory: Dict[str, Any] = {}

    def read(self) -> Dict[str, Any]:
        """Return the current contents (a fresh copy when file-backed)."""
        if self._path is None:
            return self._memory
        return read_json_dict(self._path)

    def update(self, mutate: Callable[[Dict[str, Any]], _Result]) -> _Result:
        """Apply ``mutate`` to the current contents and persist them."""
        if self._path is None:
            return mutate(self._memory)
        with _file_lock(self._path):
            data = read_json_dict(self._path)
            result = mutate(data)
            write_json_dict(self._path, data)
        return result
