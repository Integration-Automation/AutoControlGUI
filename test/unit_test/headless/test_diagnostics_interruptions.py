"""Explicit diagnostic cancellation must stop every entry point before the next active check."""
import asyncio
from concurrent.futures import CancelledError
from types import SimpleNamespace

import pytest

import je_auto_control
from je_auto_control import api
from je_auto_control.utils.diagnostics import __main__ as diagnostics_cli
from je_auto_control.utils.diagnostics import diagnostics
from je_auto_control.utils.exception.control_signals import OperationCancelledError


def _interruption(kind):
    return {
        'keyboard': KeyboardInterrupt(),
        'exit': SystemExit(7),
        'generator': GeneratorExit(),
        'async': asyncio.CancelledError(),
        'future': CancelledError(),
        'operation': OperationCancelledError('controlled diagnostic'),
    }[kind]


@pytest.mark.parametrize('entry', [diagnostics.run_diagnostics, je_auto_control.run_diagnostics,
                                  api.run_diagnostics, diagnostics_cli.main],
                         ids=['core', 'root', 'sdk', 'cli'])
@pytest.mark.parametrize('kind', ['keyboard', 'exit', 'generator', 'async', 'future', 'operation'])
@pytest.mark.parametrize('wrapped', [False, True])
def test_a_cancelled_check_preserves_original_control_and_stops_all_later_checks(monkeypatch, entry, kind, wrapped):
    original = _interruption(kind)
    failure = RuntimeError('controlled provider wrapper') if wrapped else original
    if wrapped:
        failure.__cause__ = original
    events, warnings = [], []

    def before():
        events.append('before')
        return diagnostics.Check('before', True, 'info', 'controlled')

    def stopped():
        events.append('cancelled')
        raise failure

    def later():
        events.append('later')
        return diagnostics.Check('later', True, 'info', 'controlled')

    monkeypatch.setattr(diagnostics, '_ALL_CHECKS', (before, stopped, later))
    monkeypatch.setattr(diagnostics, 'autocontrol_logger', SimpleNamespace(warning=lambda *args: warnings.append(args)))
    with pytest.raises(type(original)) as caught:
        entry()
    assert caught.value is original
    assert events == ['before', 'cancelled'] and warnings == []


@pytest.mark.parametrize('error_type', [RuntimeError, ValueError, OSError])
@pytest.mark.parametrize('cycle', [False, True])
def test_ordinary_probe_failures_still_become_report_rows_and_allow_later_checks(monkeypatch, error_type, cycle):
    failure = error_type('controlled ordinary failure')
    if cycle:
        failure.__cause__ = failure
    events, warnings = [], []

    def broken():
        events.append('broken')
        raise failure

    def later():
        events.append('later')
        return diagnostics.Check('later', True, 'info', 'controlled')

    monkeypatch.setattr(diagnostics, '_ALL_CHECKS', (broken, later))
    monkeypatch.setattr(diagnostics, 'autocontrol_logger', SimpleNamespace(warning=lambda *args: warnings.append(args)))
    report = diagnostics.run_diagnostics()
    assert events == ['broken', 'later'] and len(warnings) == 1
    assert report.to_dict() == {
        'ok': False,
        'checks': [
            {'name': 'broken', 'ok': False, 'severity': 'error',
             'detail': f'check raised: {failure!r}', 'extra': {}},
            {'name': 'later', 'ok': True, 'severity': 'info', 'detail': 'controlled', 'extra': {}},
        ],
        'count': 2,
        'failed': 1,
    }
