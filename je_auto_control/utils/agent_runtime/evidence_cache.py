"""Database-bound evidence paths never turn historical journal references into filesystem ownership."""
from __future__ import annotations

from contextlib import nullcontext
from hashlib import sha256
import os
from pathlib import Path
import re
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError

_CONTAINER = '.agent-evidence-cache'


def _directory(path: Path) -> None:
    if path.is_symlink() or path.resolve() != path or (path.exists() and not path.is_dir()):
        raise AgentTaskError('task artifact directory escapes its owner cache')


class EvidenceCache:
    """Bind cache identity to a persistent database nonce and its complete canonical path."""

    def __init__(self, store: Any) -> None:
        self.store = store
        self._identity: str | None = None

    def _identity_value(self, connection: Any = None) -> str:
        reading = self.store.connection() if connection is None else nullcontext(connection)
        with reading as current:
            row = current.execute('SELECT nonce FROM agent_evidence_identity WHERE singleton=1').fetchone()
        if row is None or not isinstance(row[0], str) or re.fullmatch('[0-9a-f]{32}', row[0]) is None:
            raise AgentTaskError('task artifact database identity requires review')
        if self._identity is not None and self._identity != row[0]:
            raise AgentTaskError('task artifact database identity changed; review required')
        self._identity = row[0]
        return row[0]

    def check_identity(self, connection: Any) -> None:
        """Recheck the actual writer's state before accepting a new provenance segment."""
        self._identity_value(connection)

    @property
    def root(self) -> Path:
        """Keep copied identities separate at different paths and preserve exact same-path restarts."""
        value = (self.store.path + '\0' + self._identity_value()).encode('utf-8')
        return Path(self.store.path).parent / _CONTAINER / sha256(value).hexdigest()

    def directory(self, task_id: str) -> Path:
        """Validate the current namespace and task directory before any artifact effect."""
        if not isinstance(task_id, str) or re.fullmatch('[0-9a-f]{32}', task_id) is None:
            raise AgentTaskError('invalid task artifact identifier')
        root = self.root
        _directory(root)
        path = root / task_id
        _directory(path)
        return path

    def file(self, task_id: str, name: str) -> Path:
        """Reject redirected, nonregular or multiply linked current artifact files."""
        if name not in {'journal.jsonl', 'journal.jsonl.lock', 'report.json'} and re.fullmatch(
                '[0-9a-f]{32}\\.jpg', name) is None:
            raise AgentTaskError('invalid task artifact filename')
        path = self.directory(task_id) / name
        if path.is_symlink() or path.resolve() != path:
            raise AgentTaskError('task artifact file escapes its owner cache')
        if path.exists() and (not path.is_file() or path.stat().st_nlink != 1):
            raise AgentTaskError('task artifact file ownership requires review')
        return path

    def is_private(self, path: Path) -> bool:
        """Protect current, legacy and actually retained historical roots without reading their files."""
        database = Path(self.store.path)
        if any(path.is_relative_to(root) for root in
               (database.parent / _CONTAINER, database.with_suffix('.evidence'))):
            return True
        for parent in path.parents:
            if parent.name.endswith('.evidence') or parent.parent.name == _CONTAINER:
                if self._recorded_root(parent):
                    return True
        return False

    def _recorded_root(self, path: Path) -> bool:
        prefix = str(path) + os.sep
        with self.store.connection() as connection:
            if connection.execute("SELECT 1 FROM sqlite_master WHERE name='run_journals'").fetchone() is None:
                return False
            return connection.execute(
                "SELECT 1 FROM run_journals j JOIN runs r ON r.id=j.run_id "
                "WHERE r.source_id='agent:'||j.journal_run_id "
                "AND substr(j.journal_path,1,?)=? COLLATE NOCASE LIMIT 1", (len(prefix), prefix)).fetchone() is not None
