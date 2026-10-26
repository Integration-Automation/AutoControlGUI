"""Service-owned task provenance, redacted artifacts and thirty-day metadata retention."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from je_auto_control.utils.action_journal.events import ActionEvent, EventStatus
from je_auto_control.utils.action_journal.store import ActionJournal
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.evidence_cache import EvidenceCache
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec, TERMINAL
from je_auto_control.utils.agent_runtime.policy import durable_payload
from je_auto_control.utils.agent_runtime.receipts import row_report
from je_auto_control.utils.json_store.json_store import atomic_write_text
from je_auto_control.utils.run_history.history_store import HistoryStore
from je_auto_control.utils.sqlite_support import last_row_id


class TaskEvidence:
    """Own only artifacts under this runtime's cache; user output files and external journals stay separate."""

    def __init__(self, store: Any) -> None:
        self.store = store
        path = Path(store.path)
        self.cache = EvidenceCache(store)
        self.history = HistoryStore(path)

    @property
    def root(self) -> Path:
        """Return the current database-bound cache, distinct from historical journal locations."""
        return self.cache.root

    def directory(self, task_id: str) -> Path:
        """Resolve a generated task directory, refusing symlink escapes even during cleanup."""
        return self.cache.directory(task_id)

    def ensure(self, task_id: str) -> dict[str, Any]:
        """Create one history link and private artifact directory, idempotently after restart."""
        journal = self.cache.file(task_id, 'journal.jsonl')
        with self.store.connection() as connection:
            current = self._current_link(connection, task_id, journal)
        if current is not None:
            if not journal.is_file():
                raise AgentTaskError('owned task journal is missing; review required')
            return current
        self.history.list_runs(limit=1)  # initialize the existing history schema before the shared transaction
        directory = self.directory(task_id)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        journal = self.cache.file(task_id, 'journal.jsonl')
        journal.touch(mode=0o600, exist_ok=True)
        with self.store.connection(write=True) as connection:
            self.cache.check_identity(connection)
            current = self._current_link(connection, task_id, journal)
            if current is not None:
                return current
            cursor = connection.execute("INSERT INTO runs(source_type,source_id,script_path,started_at,status) "
                                        "VALUES ('manual',?,'',?,'running')", ("agent:" + task_id, time.time()))
            run_id = last_row_id(cursor)
            connection.execute("INSERT INTO run_journals VALUES (?,?,?)", (run_id, str(journal), task_id))
            connection.execute('INSERT INTO agent_evidence VALUES (?,?,?) ON CONFLICT(task_id) DO UPDATE '
                               'SET history_id=excluded.history_id,journal_path=excluded.journal_path',
                               (task_id, run_id, str(journal)))
            self.cache.check_identity(connection)
            if self._current_link(connection, task_id, journal) != {
                    'task_id': task_id, 'history_id': run_id, 'journal_path': str(journal)}:
                raise AgentTaskError('task artifact history ownership changed; review required')
        return {"task_id": task_id, "history_id": run_id, "journal_path": str(journal)}

    @staticmethod
    def _current_link(connection: Any, task_id: str, journal: Path) -> dict | None:
        row = connection.execute('SELECT * FROM agent_evidence WHERE task_id=?', (task_id,)).fetchone()
        if row is None or Path(row['journal_path']) != journal:
            return None
        linked = connection.execute('SELECT 1 FROM runs r JOIN run_journals j ON r.id=j.run_id '
                                    'WHERE r.id=? AND r.source_id=? AND j.journal_path=? AND j.journal_run_id=?',
                                    (row['history_id'], 'agent:' + task_id, str(journal), task_id)).fetchone()
        return dict(row) if linked is not None else None

    def metadata(self, task_id: str) -> dict[str, Any]:
        """Read provenance without creating artifacts as a side effect of a status request."""
        with self.store.connection() as connection:
            row = connection.execute("SELECT * FROM agent_evidence WHERE task_id=?", (task_id,)).fetchone()
            pending = connection.execute("SELECT 1 FROM agent_evidence_pending WHERE task_id=?", (task_id,)).fetchone()
            completion = connection.execute(
                "SELECT contract FROM agent_completion WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            return {}
        directory = self.directory(task_id)
        paths = directory.iterdir() if directory.exists() else ()
        artifacts = [str(path) for path in paths if path.is_file() and not path.is_symlink()]
        return {"history_path": self.history.path, "history_id": row["history_id"],
                "journal_path": row["journal_path"], "artifacts": sorted(artifacts),
                "artifact_cache_state": "owned" if Path(row['journal_path']) == directory / 'journal.jsonl'
                else "historical",
                "report_pending": pending is not None, "completion_contract": completion[0] if completion else 0}

    def defer(self, task_ids: list[str]) -> None:
        """Persist publication work so large emergency stops can acknowledge input retirement promptly."""
        with self.store.connection(write=True) as connection:
            connection.executemany("INSERT OR IGNORE INTO agent_evidence_pending VALUES (?)",
                                   [(identifier,) for identifier in task_ids])

    def flush(self, limit: int = 8) -> None:
        """Publish a bounded batch; interrupted publication remains durable for the next service owner."""
        with self.store.connection() as connection:
            identifiers = [row[0] for row in connection.execute("SELECT task_id FROM agent_evidence_pending LIMIT ?",
                                                               (limit,))]
        for task_id in identifiers:
            self.publish(task_id)

    def action(self, task_id: str, receipt: dict[str, Any], *, finished: bool = False) -> None:
        """Mirror receipt certainty into the existing append-only action journal."""
        self.ensure(task_id)
        journal = self.cache.file(task_id, 'journal.jsonl')
        self.cache.file(task_id, 'journal.jsonl.lock')
        status: EventStatus = "incomplete" if not finished else (
            "ok" if receipt["status"] == "confirmed" else "error")
        ActionJournal(journal).append(ActionEvent(
            run_id=task_id, step_id=receipt["id"], command=receipt["command"],
            parameters=durable_payload(receipt["arguments"]), started_at=receipt["created"],
            finished_at=max(time.time(), receipt["created"]) if finished else None,
            status=status, outcome=durable_payload(receipt.get("result")),
            non_replayable=_replay_reasons(receipt)))

    def publish(self, task_id: str) -> None:
        """Publish scrubbed structured results and link the shared history schema to this task."""
        row = self.store.get(task_id)
        link = self.ensure(task_id)
        receipts = self.store.actions(task_id)
        spec = AgentTaskSpec.from_dict(row["spec"])
        report = {"task_id": task_id, "state": row["state"], "reason": row["reason"],
                  "verification": row["verification"], "rows": row_report(spec, receipts),
                  "action_count": len(receipts), "actions": [_summary(item) for item in receipts[-1000:]]}
        destination = self.cache.file(task_id, 'report.json')
        atomic_write_text(destination, json.dumps(durable_payload(report), ensure_ascii=False, indent=2))
        destination.chmod(0o600)
        if row["state"] in TERMINAL or row["state"] == "waiting_user":
            self.history.finish_run(link["history_id"], "ok" if row["state"] == "succeeded" else "error",
                                    row["reason"] or row["state"], artifact_path=str(destination))
        with self.store.connection(write=True) as connection:
            connection.execute("DELETE FROM agent_evidence_pending WHERE task_id=? AND EXISTS "
                               "(SELECT 1 FROM agent_tasks WHERE id=? AND updated=?)",
                               (task_id, task_id, row["updated"]))

    def image(self, task_id: str, observation_id: str, image: dict) -> None:
        """Persist only explicitly opted-in, strict-redacted target images under generated names."""
        if image.get("redacted_by") != "strict" or image.get("format") != "jpeg":
            raise AgentTaskError("persistent task images require strict target redaction")
        if re.fullmatch(r"[0-9a-f]{32}", observation_id) is None:
            raise AgentTaskError("invalid observation artifact identifier")
        data = base64.b64decode(image["data"], validate=True)
        _verify_image(data)
        self.ensure(task_id)
        directory = self.directory(task_id)
        if sum(1 for _path in directory.glob("*.jpg")) >= 100:
            raise AgentTaskError("persistent task images exceed the one-hundred artifact limit")
        path = self.cache.file(task_id, observation_id + '.jpg')
        with path.open("xb") as handle:
            handle.write(data)
        path.chmod(0o600)

    def remove(self, task_id: str) -> None:
        """Remove only recognized owned artifacts and the matching private history row."""
        directory = self.directory(task_id)
        if directory.exists():
            paths = list(directory.iterdir())
            if any(not _owned_artifact(path) for path in paths):
                raise AgentTaskError("task cache contains unrecognized data; retention needs review")
            for path in paths:
                self.cache.file(task_id, path.name)
            for path in paths:
                self.cache.file(task_id, path.name).unlink()
            self.directory(task_id).rmdir()
        if Path(self.history.path).exists():
            with self.store.connection(write=True) as connection:
                identifiers = [row[0] for row in connection.execute("SELECT id FROM runs WHERE source_id=?",
                                                                   ("agent:" + task_id,))]
                for identifier in identifiers:
                    connection.execute("DELETE FROM run_journals WHERE run_id=?", (identifier,))
                    connection.execute("DELETE FROM runs WHERE id=?", (identifier,))


def _owned_artifact(path: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    return path.name in {"journal.jsonl", "journal.jsonl.lock", "report.json"} or (
        re.fullmatch(r"[0-9a-f]{32}\.jpg", path.name) is not None)


def _summary(receipt: dict) -> dict:
    outcome = json.dumps(receipt["result"], sort_keys=True).encode("utf-8")
    result = {"id": receipt["id"], "command": receipt["command"], "status": receipt["status"],
              "created": receipt["created"], "result_sha256": hashlib.sha256(outcome).hexdigest()}
    if "grounding" in receipt:
        result["grounding"] = receipt["grounding"]
    return result


def _replay_reasons(receipt: dict) -> tuple[str, ...]:
    if receipt.get("reviewed_by"):
        return ("owner reviewed outcome",)
    return ("uncertain effect",) if receipt["status"] == "uncertain" else ()


def _verify_image(data: bytes) -> None:
    from je_auto_control.utils.agent_runtime.images import verify_jpeg
    verify_jpeg(data)
