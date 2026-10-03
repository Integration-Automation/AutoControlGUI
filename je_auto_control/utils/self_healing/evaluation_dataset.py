"""Load root-checked labelled frames and export JSON plus shareable HTML reports."""
from __future__ import annotations

import html
import io
import json
from pathlib import Path
from typing import Dict, Tuple, Union, cast

from je_auto_control.utils.action_journal.events import JSONValue, safe_payload
from je_auto_control.utils.json_store.json_store import atomic_write_text
from je_auto_control.utils.path_guard.policy import scoped_path
from je_auto_control.utils.self_healing.evaluation_models import Box, EvaluationSample, HealingEvaluationError, Point
from je_auto_control.utils.self_healing.report_views import comparison_tables


def json_object(value: object) -> Dict[str, JSONValue]:
    """Require finite JSON mapping data without coercing arbitrary objects."""
    copied, reasons = safe_payload(value)
    if reasons or not isinstance(copied, dict):
        raise HealingEvaluationError('configuration must be a finite JSON object')
    return copied


def load_evaluation_dataset(path: Union[str, Path]) -> Tuple[EvaluationSample, ...]:
    """Load schema-one samples once; all versions use the same immutable bytes."""
    source = scoped_path(path, operation='read')
    try:
        data = json_object(json.loads(source.read_text(encoding='utf-8')))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise HealingEvaluationError('cannot read the fixed-frame dataset') from error
    if isinstance(data.get('schema_version'), bool) or data.get('schema_version') != 1:
        raise HealingEvaluationError('unsupported evaluation dataset schema')
    rows = data.get('samples')
    if not isinstance(rows, list) or not rows:
        raise HealingEvaluationError('dataset requires nonempty sample rows')
    return tuple(_sample(json_object(row), source.parent) for row in rows)


def _numbers(value: JSONValue, length: int) -> Tuple[float, ...]:
    if not isinstance(value, list) or len(value) != length:
        raise HealingEvaluationError('geometry must be an array with the expected dimensions')
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value):
        raise HealingEvaluationError('geometry must contain numbers')
    return tuple(float(cast(Union[int, float], item)) for item in value)


def _sample(row: Dict[str, JSONValue], directory: Path) -> EvaluationSample:
    # pylint: disable-next=import-outside-toplevel  # reason: Pillow is loaded only when frames are inspected
    from PIL import Image
    frame_path = row.get('frame_path')
    if not isinstance(frame_path, str) or not frame_path:
        raise HealingEvaluationError('sample requires a frame_path')
    try:
        frame = scoped_path(directory / frame_path, operation='read').read_bytes()
        with Image.open(io.BytesIO(frame)) as image:
            image.verify()
    except (OSError, ValueError) as error:
        raise HealingEvaluationError('sample frame is not a valid readable image') from error
    expected = row.get('expected_box')
    box = cast(Box, _numbers(expected, 4)) if expected is not None else None
    identifier, negative, verified = row.get('sample_id', frame_path), row.get('expected_miss', False), row.get(
        'operation_verified')
    if not isinstance(identifier, str) or not isinstance(negative, bool):
        raise HealingEvaluationError('sample identity or expected_miss is invalid')
    if verified is not None and not isinstance(verified, bool):
        raise HealingEvaluationError('operation_verified must be boolean or unknown')
    context = _sample_context(row, str(scoped_path(directory / frame_path, operation='read')))
    return EvaluationSample(frame, box, cast(Point, _numbers(row.get('origin', [0, 0]), 2)),
                            cast(Point, _numbers(row.get('scale', [1, 1]), 2)), negative, identifier, verified, context)


def _sample_context(row: Dict[str, JSONValue], source: str) -> Dict[str, str]:
    values = json_object(row.get('context', {}))
    if any(not isinstance(value, str) for value in values.values()):
        raise HealingEvaluationError('sample context must contain text identities')
    context = {key: cast(str, value) for key, value in values.items()}
    context['frame_path'] = source
    return context


def write_comparison_report(report: Dict[str, JSONValue], path: Union[str, Path]) -> None:
    """Write finite JSON and an escaped HTML report; no frames or executable content."""
    target = scoped_path(path, operation='write')
    page = scoped_path(target.with_suffix('.html'), operation='write')
    if target.suffix.lower() != '.json' or target == page:
        raise HealingEvaluationError('comparison report destination must end in .json')
    scoped_path(target.parent, operation='write').mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2)
    atomic_write_text(target, text)
    atomic_write_text(page, '<!doctype html><meta charset="utf-8"><title>Locator comparison</title>'
                      '<h1>Fixed-frame locator comparison</h1>' + comparison_tables(report)
                      + '<details><summary>Full evidence</summary><pre>' + html.escape(text) + '</pre></details>')
