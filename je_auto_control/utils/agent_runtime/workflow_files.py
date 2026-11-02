"""Rooted, bounded and idempotent download/archive operations for managed workflows."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.request import HTTPRedirectHandler, Request, build_opener

from je_auto_control.utils.agent_runtime.context import current_operation
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.policy import TaskPolicy, durable_payload
from je_auto_control.utils.agent_runtime.workflow_specs import url_origin

_LIMIT = 16 * 1024 * 1024


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def task_policy() -> TaskPolicy:
    """Require host-bound authority; these operations cannot create their own scope."""
    context = current_operation()
    if context is None:
        raise AgentTaskError("workflow operations require a managed task")
    context.checkpoint()
    return TaskPolicy(context.spec)


def _destination(policy: TaskPolicy, directory: str, name: str) -> Path:
    if not isinstance(name, str) or not name or Path(name).name != name or "\\" in name or ":" in name:
        raise AgentTaskError("archive names must be plain filenames")
    if name.endswith((".part", ".crdownload", ".tmp")):
        raise AgentTaskError("archive names cannot be temporary downloads")
    _portable_name(name)
    return Path(policy.path(str(Path(policy.path(directory)) / name)))


def _portable_name(name: str) -> None:
    if name != name.rstrip(" .") or any(character in name for character in '<>"|?*\r\n\x00'):
        raise AgentTaskError("archive name is not portable")
    reserved = {"CON", "PRN", "AUX", "NUL", *[f"COM{number}" for number in range(1, 10)],
                *[f"LPT{number}" for number in range(1, 10)]}
    if name.split(".", 1)[0].upper() in reserved:
        raise AgentTaskError("archive name is a reserved device")


def workflow_download(url: str, directory: str, name: str, sha256: str = "") -> dict[str, Any]:
    """Download an approved URL without redirects and archive a verified complete file."""
    policy = task_policy()
    if url_origin(url) not in policy.spec.options.get("allowed_origins", ()):
        raise AgentTaskError("download origin was not preauthorized")
    from je_auto_control.utils.egress.egress_policy import get_egress_policy
    get_egress_policy().check(url)
    path = _destination(policy, directory, name)
    if path.is_file():
        if not sha256 or _digest(path) != sha256:
            raise AgentTaskError("existing download requires matching sha256 before reuse")
        return _entry(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with build_opener(_NoRedirect()).open(Request(url, headers={"Accept-Encoding": "identity"}),
                                        timeout=policy.spec.budget.action_seconds) as response:
        return _receive(response, path, sha256)


def _receive(response: Any, path: Path, expected: str) -> dict[str, Any]:
    length = response.headers.get("Content-Length")
    size = 0
    handle = tempfile.NamedTemporaryFile(dir=path.parent, prefix=".agent-", suffix=".part", delete=False)
    temporary = Path(handle.name)
    try:
        with handle:
            while True:
                task_policy()
                data = response.read(65536)
                if not data:
                    break
                size += len(data)
                if size > _LIMIT:
                    raise AgentTaskError("download exceeds sixteen megabytes")
                handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if not size or (length is not None and size != int(length)):
            raise AgentTaskError("download is empty or incomplete")
        if expected and _digest(temporary) != expected:
            raise AgentTaskError("download sha256 does not match")
        task_policy().path(str(path))
        os.link(temporary, path)
        return _entry(path)
    finally:
        temporary.unlink(missing_ok=True)


def _digest(path: Path) -> str:
    if path.stat().st_size > _LIMIT:
        raise AgentTaskError("archive file exceeds sixteen megabytes")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for data in iter(lambda: handle.read(65536), b""):
            digest.update(data)
    return digest.hexdigest()


def _entry(path: Path) -> dict[str, Any]:
    return {"path": str(path), "name": path.name, "bytes": path.stat().st_size, "sha256": _digest(path)}


def workflow_manifest(directory: str, path: str, names: list[str]) -> dict[str, Any]:
    """Write a bounded archive manifest without replacing existing, different content."""
    policy = task_policy()
    if not isinstance(names, list) or not 1 <= len(names) <= 500:
        raise AgentTaskError("manifest requires between 1 and 500 filenames")
    entries = [_entry(_destination(policy, directory, name)) for name in names]
    destination = Path(policy.path(path))
    content = json.dumps(durable_payload({"files": entries}), ensure_ascii=False, sort_keys=True, indent=2)
    if destination.exists():
        if destination.read_text(encoding="utf-8") != content:
            raise AgentTaskError("manifest exists with different content")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8") as handle:
            handle.write(content)
    return {"manifest": str(destination), "files": entries, "count": len(entries)}
