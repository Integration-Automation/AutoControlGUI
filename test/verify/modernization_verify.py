"""Produce controlled cross-layer acceptance evidence without native input or network."""
from __future__ import annotations

import argparse
import json
import os
from importlib.metadata import version
import platform
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import patch

import je_auto_control as ac
from je_auto_control.utils.action_journal import read_events
from je_auto_control.utils.executor.action_executor import Executor


class AcceptanceError(ac.AutoControlException, ValueError):
    """An acceptance report has an invalid or unsupported evidence claim."""


def journal_round_trip(folder: Path) -> dict[str, Any]:
    """Record, generate and execute Python against an explicitly controlled device sink."""
    folder.mkdir(parents=True, exist_ok=True)
    source_id, replay_id = 'source-' + uuid.uuid4().hex, 'replay-' + uuid.uuid4().hex
    source = ac.ActionJournal(folder / 'source.jsonl')
    executor = Executor()
    results: list[list[int]] = []

    def device_move(x: int, y: int) -> None:
        results.append([x, y])

    executor.event_dict['AC_set_mouse_position'] = device_move
    with source.run(run_id=source_id, device='controlled-device', source='acceptance fixture'):
        executor.execute_action([['AC_set_mouse_position', {'x': 12, 'y': 24}]], raise_on_error=True)
    candidate = ac.generate_candidate_from_log(source.path, run_id=source_id, target='python', name='replay')
    results.clear()
    replay = ac.ActionJournal(folder / 'replayed.jsonl')
    namespace: dict[str, Any] = {'__name__': 'controlled_candidate'}
    with patch.object(ac, 'executor', executor):
        # pylint: disable-next=exec-used  # reason: generated fixture runs only against the patched executor sink
        exec(compile(candidate.code, '<controlled-candidate>', 'exec'), namespace)  # nosec B102
        with replay.run(run_id=replay_id, device='controlled-device', source=str(source.path)):
            namespace['replay']()
    original = read_events(source.path, run_id=source_id)
    repeated = read_events(replay.path, run_id=replay_id)
    source_steps = [[row.command, row.arguments, row.device] for row in original if row.status == 'ok']
    replayed_steps = [[row.command, row.arguments, row.device] for row in repeated if row.status == 'ok']
    return {'source_steps': source_steps, 'replayed_steps': replayed_steps, 'device_results': results,
            'manifest': candidate.manifest, 'mode': 'controlled',
            'source_run_id': source_id, 'replay_run_id': replay_id,
            'evidence': [str(source.path), str(replay.path)]}


def sync_restart(folder: Path) -> dict[str, Any]:
    """Commit, close, reopen and retry one durable bucket without a transport."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'sync.sqlite'
    bucket = ac.ConfigBucket('acceptance', {'hotkeys': {'one': {'combo': 'ctrl+k', 'last_modified': 1}}})
    store = ac.ConfigStore(path)
    try:
        revision = store.commit('acceptance', bucket, base_revision=0, operation_id='acceptance-edit')
    finally:
        store.close()
    reopened = ac.ConfigStore(path)
    try:
        retry = reopened.commit('acceptance', bucket, base_revision=0, operation_id='acceptance-edit')
        saved = reopened.get('acceptance')
        if saved is None:
            raise ac.ConfigSyncError('committed acceptance bucket disappeared')
        reopened_revision = saved.revision
    finally:
        reopened.close()
    return {'revision': reopened_revision, 'committed_revision': revision,
            'reopened_revision': reopened_revision, 'retry_revision': retry, 'evidence': [str(path)]}


def validate_report(report: dict[str, Any]) -> None:
    """Reject unsupported verification claims and skipped checks without reasons."""
    if not all(report.get(key) for key in ('platform', 'backend', 'versions')):
        raise AcceptanceError('acceptance report requires platform/backend/versions')
    for row in report['checks']:
        if row['status'] == 'verified' and (not row.get('evidence')
                                           or not all(Path(item).is_file() for item in row['evidence'])):
            raise AcceptanceError('verified check requires evidence')
        if row['status'] == 'skipped' and not row.get('reason'):
            raise AcceptanceError('skipped check requires reason')
        if row['status'] not in ('verified', 'skipped', 'failed'):
            raise AcceptanceError('unknown acceptance status')


def acceptance_report(folder: Path) -> dict[str, Any]:
    """Run controlled workflows and explicitly retain untested native boundaries."""
    journal = journal_round_trip(folder / 'journal')
    sync = sync_restart(folder / 'sync')
    checks = [
        {'name': 'journal-generated-device-result',
         'status': 'verified' if journal['source_steps'] == journal['replayed_steps']
         and journal['device_results'] == [[12, 24]] else 'failed',
         'evidence': journal['evidence'], 'mode': 'controlled',
         'actual': {key: journal[key] for key in ('source_run_id', 'replay_run_id', 'source_steps',
                                                 'replayed_steps', 'device_results')}},
        {'name': 'durable-sync-restart', 'status': 'verified' if
         sync['revision'] == sync['committed_revision'] == sync['retry_revision'] else 'failed',
         'evidence': sync['evidence'], 'mode': 'local-sqlite',
         'actual': {key: sync[key] for key in ('revision', 'committed_revision', 'retry_revision')}},
    ]
    for name, reason in (
        ('native-desktop', 'No human consent or physical keyboard exercised by this verifier.'),
        ('physical-mobile', 'No physical Android device or remote WDA endpoint configured.'),
        ('two-host-sync', 'This verifier uses one local SQLite store, without network transport.'),
        ('downstream-editable', 'Production editable application integration is a separate acceptance step.'),
    ):
        checks.append({'name': name, 'status': 'skipped', 'evidence': [], 'reason': reason})
    report = {'schema_version': 1, 'platform': platform.platform(), 'backend': 'controlled-executor/local-sqlite',
              'versions': {'python': platform.python_version(), 'package': version('je-auto-control')},
              'source_commit': os.environ.get('GITHUB_SHA', 'local-worktree'), 'checks': checks}
    validate_report(report)
    return report


def main() -> int:
    """Write a machine-readable report into an explicitly selected artifact directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = acceptance_report(args.output)
    (args.output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return int(any(row['status'] == 'failed' for row in report['checks']))


if __name__ == '__main__':
    raise SystemExit(main())
