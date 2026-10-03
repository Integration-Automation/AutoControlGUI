"""Explicitly validate, accept and revert immutable candidate template revisions."""
from __future__ import annotations

import hashlib
import io
import json
import re
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterator, Sequence, Union

from je_auto_control.utils.action_journal.events import JSONValue, safe_payload
from je_auto_control.utils.json_store.json_store import _file_lock, atomic_write_bytes, atomic_write_text
from je_auto_control.utils.path_guard.policy import scoped_path
from je_auto_control.utils.self_healing.evaluation import evaluate_locators
from je_auto_control.utils.self_healing.evaluation_models import (
    EvaluationSample, HealingComparison, HealingEvaluationError,
)
from je_auto_control.utils.self_healing.frame_strategies import TemplateFrameStrategy


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _text(row: Dict[str, JSONValue], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise HealingEvaluationError('invalid template revision metadata: ' + key)
    return value


def _image_bytes(path: Path) -> bytes:
    # pylint: disable-next=import-outside-toplevel  # reason: Pillow is loaded only for template inspection
    from PIL import Image
    try:
        data = scoped_path(path, operation='read').read_bytes()
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
    except (OSError, ValueError) as error:
        raise HealingEvaluationError('template must contain a valid image') from error
    return data


class TemplateRevisionStore:
    """A root-checked revision directory; no proposed image is automatically applied."""

    def __init__(self, path: Union[str, Path]) -> None:
        if not str(path).strip():
            raise HealingEvaluationError('template revision store_path must be nonempty')
        self.path = scoped_path(path, operation='read')
        if self.path.exists() and not self.path.is_dir():
            raise HealingEvaluationError('template revision store_path must name a directory')
        self._index = self.path / 'index.json'
        self._lock = threading.RLock()

    def _load_state(self) -> Dict[str, JSONValue]:
        path = scoped_path(self._index, operation='read')
        if not path.exists():
            return {'schema_version': 1, 'revisions': {}}
        try:
            data, reasons = safe_payload(json.loads(path.read_text('utf-8')))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise HealingEvaluationError('cannot read template revision metadata') from error
        if (reasons or not isinstance(data, dict) or data.get('schema_version') != 1
                or not isinstance(data.get('revisions'), dict)):
            raise HealingEvaluationError('unsupported template revision metadata')
        return data

    @contextmanager
    def _state(self) -> Iterator[Dict[str, JSONValue]]:
        path = scoped_path(self._index, operation='write')
        scoped_path(path.with_name(path.name + '.lock'), operation='write')
        self.path.mkdir(parents=True, exist_ok=True)
        with self._lock, _file_lock(path):
            yield self._load_state()

    def _save(self, data: Dict[str, JSONValue]) -> None:
        scoped_path(self.path, operation='write')
        atomic_write_text(scoped_path(self._index, operation='write'),
                          json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2))

    def _snapshot_path(self, identifier: str, kind: str) -> Path:
        if re.fullmatch(r'[0-9a-f]{32}', identifier) is None:
            raise HealingEvaluationError('invalid template revision identity')
        return self.path / (identifier + '-' + kind + '.png')

    def _row(self, data: Dict[str, JSONValue], identifier: str) -> Dict[str, JSONValue]:
        self._snapshot_path(identifier, 'candidate')
        rows = data.get('revisions')
        row = rows.get(identifier) if isinstance(rows, dict) else None
        if not isinstance(row, dict):
            raise HealingEvaluationError('unknown template revision')
        return row

    def propose(self, template_path: Path, candidate_path: Path) -> str:
        """Snapshot both images without replacing the user's current template."""
        target = scoped_path(template_path, operation='read')
        original, candidate = _image_bytes(target), _image_bytes(candidate_path)
        identifier = uuid.uuid4().hex
        with self._state() as data:
            for kind, content in [('base', original), ('candidate', candidate)]:
                atomic_write_bytes(scoped_path(self._snapshot_path(identifier, kind), operation='write'), content)
            rows = data['revisions']
            if not isinstance(rows, dict):
                raise HealingEvaluationError('invalid revisions mapping')
            rows[identifier] = {'revision_id': identifier, 'target': str(target), 'status': 'candidate',
                                'base_hash': _hash(original), 'candidate_hash': _hash(candidate)}
            self._save(data)
        return identifier

    def preview(self, identifier: str) -> Dict[str, JSONValue]:
        """Return checked preview paths, content identities and any validation report."""
        with self._lock:
            row = dict(self._row(self._load_state(), identifier))
            self._verified_snapshot(row, identifier, 'base')
            self._verified_snapshot(row, identifier, 'candidate')
            row['base_path'] = str(scoped_path(self._snapshot_path(identifier, 'base'), operation='read'))
            row['candidate_path'] = str(scoped_path(self._snapshot_path(identifier, 'candidate'), operation='read'))
            scoped_path(_text(row, 'target'), operation='read')
            return row

    def _verified_snapshot(self, row: Dict[str, JSONValue], identifier: str, kind: str) -> bytes:
        value = _image_bytes(self._snapshot_path(identifier, kind))
        if _hash(value) != _text(row, kind + '_hash'):
            raise HealingEvaluationError('template revision snapshot changed')
        return value

    def validate(self, identifier: str, samples: Sequence[EvaluationSample],
                 threshold: float = 0.99) -> HealingComparison:
        """Compare immutable base/candidate images and persist an explicit acceptance decision."""
        with self._state() as data:
            row = self._row(data, identifier)
            if row.get('status') not in {'candidate', 'validated'}:
                raise HealingEvaluationError('only pending candidates may be validated')
            for kind in ('base', 'candidate'):
                self._verified_snapshot(row, identifier, kind)
            comparison = evaluate_locators(samples, {
                kind: TemplateFrameStrategy(str(self._snapshot_path(identifier, kind)), threshold)
                for kind in ('base', 'candidate')})
            report = comparison.versions['candidate']
            positive_hits = sum(trial.correct is True and trial.expected_present is True for trial in report.trials)
            row['validation'] = comparison.to_dict()
            row['validated_hash'] = row['candidate_hash']
            row['validation_passed'] = (report.accuracy.value == 1 and report.false_positive == 0
                                        and report.errors == 0 and positive_hits > 0)
            row['status'] = 'validated'
            self._save(data)
            return comparison

    def accept(self, identifier: str) -> Dict[str, JSONValue]:
        """Apply a successfully validated candidate if the original template is unchanged."""
        with self._state() as data:
            row = self._row(data, identifier)
            if (row.get('status') != 'validated' or row.get('validation_passed') is not True
                    or row.get('validated_hash') != row.get('candidate_hash')):
                raise HealingEvaluationError('candidate requires successful labelled validation before acceptance')
            content = self._verified_snapshot(row, identifier, 'candidate')
            self._replace_target(row, content, _text(row, 'base_hash'))
            row['status'] = 'accepted'
            self._save(data)
            return dict(row)

    def revert(self, identifier: str) -> Dict[str, JSONValue]:
        """Restore the immutable base only when the accepted candidate is still current."""
        with self._state() as data:
            row = self._row(data, identifier)
            if row.get('status') not in {'accepted', 'validated'}:
                raise HealingEvaluationError('revision has not been accepted')
            content = self._verified_snapshot(row, identifier, 'base')
            self._replace_target(row, content, _text(row, 'candidate_hash'))
            row['status'] = 'reverted'
            self._save(data)
            return dict(row)

    @staticmethod
    def _replace_target(row: Dict[str, JSONValue], content: bytes, expected_hash: str) -> None:
        target = scoped_path(_text(row, 'target'), operation='write')
        scoped_path(target.parent, operation='write')
        scoped_path(target.with_name(target.name + '.lock'), operation='write')
        with _file_lock(target):
            if _hash(scoped_path(target, operation='read').read_bytes()) != expected_hash:
                raise HealingEvaluationError('current template changed; refusing to overwrite it')
            atomic_write_bytes(target, content)
