"""Independently re-read archive manifests and their scoped files at task completion."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.policy import TaskPolicy


def manifest_matches(clause: Mapping, policy: TaskPolicy) -> bool:
    """Require exact reviewed filenames, paths, sizes and current content digests, within read bounds."""
    manifest = Path(policy.path(clause["path"]))
    if not manifest.is_file():
        return False
    if manifest.stat().st_size > 1_000_000:
        raise AgentTaskError("archive manifest exceeds one megabyte")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"files"} or not isinstance(data["files"], list):
        return False
    entries, names = data["files"], list(clause["names"])
    if len(entries) != len(names):
        return False
    return _files_match(entries, names, clause, policy)


def _files_match(entries: list, names: list[str], clause: Mapping, policy: TaskPolicy) -> bool:
    from je_auto_control.utils.agent_runtime.workflow_files import _destination, _entry
    total = 0
    for name, entry in zip(names, entries):
        path = _destination(policy, clause["directory"], name)
        if not path.is_file():
            return False
        total += path.stat().st_size
        if total > 64 * 1024 * 1024:
            raise AgentTaskError("archive completion evidence exceeds sixty-four megabytes")
        if entry != _entry(path):
            return False
    return True


def validate_manifest_clause(clause: Mapping) -> None:
    """Reject incomplete or duplicate manifest filename contracts before executing a task."""
    names = clause.get("names")
    if not isinstance(names, (tuple, list)) or not 1 <= len(names) <= 500:
        raise AgentTaskError("archive evidence requires between one and five hundred names")
    if not all(isinstance(name, str) and name for name in names) or len(set(names)) != len(names):
        raise AgentTaskError("archive evidence filenames must be nonempty and unique")
    if not isinstance(clause.get("directory"), str):
        raise AgentTaskError("archive evidence requires a scoped directory")
