"""Read-only metric and failure rows shared by HTML exports and GUI reports."""
from __future__ import annotations

import html
from typing import Dict, List, Tuple

from je_auto_control.utils.action_journal.events import JSONValue

METRIC_COLUMNS = ('version', 'image_hit', 'fallback', 'miss', 'accuracy', 'false_positive_rate',
                  'recovery', 'p50_ms', 'p95_ms', 'unknown', 'cost_total')
FAILURE_COLUMNS = ('version', 'sample_id', 'step_id', 'coordinates', 'error')


def _text(value: JSONValue) -> str:
    if isinstance(value, dict) and 'denominator' in value:
        return str(value.get('numerator')) + '/' + str(value.get('denominator'))
    if isinstance(value, float):
        return f'{value:.3f}'
    return 'unknown' if value is None else str(value)


def comparison_rows(report: Dict[str, JSONValue]) -> Tuple[List[List[str]], List[List[str]]]:
    """Extract version metrics and labelled failures with original-step provenance."""
    versions = report.get('versions')
    if not isinstance(versions, dict):
        return [], []
    metrics, failures = [], []
    for name, value in versions.items():
        if not isinstance(value, dict):
            continue
        metrics.append([name] + [_text(value.get(key)) for key in METRIC_COLUMNS[1:]])
        trials = value.get('trials')
        if isinstance(trials, list):
            failures.extend(_failure_rows(name, trials))
    return metrics, failures


def _failure_rows(name: str, trials: List[JSONValue]) -> List[List[str]]:
    rows = []
    for trial in trials:
        if not isinstance(trial, dict) or (trial.get('correct') is not False and trial.get('error') is None):
            continue
        sample = trial.get('sample')
        context = sample.get('context') if isinstance(sample, dict) else None
        step = context.get('step_id') if isinstance(context, dict) else None
        rows.append([name, _text(trial.get('sample_id')), _text(step),
                     _text(trial.get('coordinates')), _text(trial.get('error'))])
    return rows


def comparison_tables(report: Dict[str, JSONValue]) -> str:
    """Render escaped, self-contained metric and failure tables without scripts."""
    metrics, failures = comparison_rows(report)
    tables = []
    for columns, rows in ((METRIC_COLUMNS, metrics), (FAILURE_COLUMNS, failures)):
        header = ''.join('<th>' + html.escape(column) + '</th>' for column in columns)
        body = ''.join('<tr>' + ''.join('<td>' + html.escape(cell) + '</td>' for cell in row) + '</tr>'
                       for row in rows)
        tables.append('<table border="1"><thead><tr>' + header + '</tr></thead><tbody>' + body + '</tbody></table>')
    return ''.join(tables)
