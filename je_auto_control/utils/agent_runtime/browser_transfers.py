"""Rooted file snapshots and atomic publication around WebRunner-owned browser transfers."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import stat
from concurrent.futures import CancelledError
from typing import Any

from je_auto_control.utils.agent_runtime.browser_validation import browser_url_origin as _url_origin
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.agent_runtime.workflow_files import (
    _destination, _digest, _entry, _portable_name, _receive, task_policy,
)

_UPLOAD_LIMIT = 4 * 1024 * 1024


def _expected(value: Any) -> str:
    if not isinstance(value, str) or (value and re.fullmatch(r"[0-9a-f]{64}", value) is None):
        raise AgentTaskError("browser file sha256 must be 64 lowercase hexadecimal characters")
    return value


def _origin(url: str) -> None:
    origins = {_url_origin(value) for value in task_policy().spec.options.get("allowed_origins", ())}
    if _url_origin(url) not in origins:
        raise AgentTaskError("browser transfer URL is outside task origins")


def _snapshot(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= _UPLOAD_LIMIT:
            raise AgentTaskError("browser upload requires a regular file from one byte to four megabytes")
        _same_file(path, before)
        data = handle.read(_UPLOAD_LIMIT + 1)
        after = os.fstat(handle.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns) or len(data) != before.st_size:
            raise AgentTaskError("browser upload file changed while reading")
        _same_file(path, after)
    return data


def _same_file(path: Path, opened: os.stat_result) -> None:
    if Path(task_policy().path(str(path))) != path:
        raise AgentTaskError("browser upload path changed outside its reviewed scope")
    current = path.stat()
    if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
            current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns):
        raise AgentTaskError("browser upload file identity changed")


def sdk_transfer(session: Any, operation: str, arguments: dict) -> Any:
    """Use only the SDK transfer contract; no browser engine or ambient HTTP client is imported."""
    if operation == "link":
        url = session.link(arguments["selector"], arguments["frame"])
        _origin(url)
        return url
    expected = _expected(arguments["sha256"])
    if operation == "download":
        _origin(arguments["url"])
        path = _destination(task_policy(), arguments["directory"], arguments["name"])
        if path.is_file():
            if not expected or _digest(path) != expected:
                raise AgentTaskError("existing browser download requires matching sha256")
            return _entry(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return _receive_download(session, arguments["url"], path, expected)
    path = Path(task_policy().path(arguments["path"]))
    _portable_name(path.name)
    data = _snapshot(path)
    if expected and hashlib.sha256(data).hexdigest() != expected:
        raise AgentTaskError("browser upload sha256 does not match")
    task_policy()
    result = session.upload(arguments["selector"], data, path.name, arguments["frame"])
    metadata = {"name": path.name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    if result != metadata:
        raise AgentTaskError("browser upload metadata does not match its rooted snapshot")
    return metadata


def _receive_download(session: Any, url: str, path: Path, expected: str) -> dict:
    # Keep host authority/cancellation errors out of the foreign SDK's broad context-manager containment.
    failure: BaseException | None = None
    result: dict = {}
    try:
        with session.open_download(url) as response:
            try:
                result = _receive(response, path, expected)
            except (AutoControlException, CancelledError) as error:
                failure = error
    finally:
        if failure is not None:
            raise failure
    return result
