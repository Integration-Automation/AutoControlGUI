"""Whole-B review regressions for confidentiality and replay/status guarantees."""
import json
from dataclasses import replace

import pytest

from je_auto_control.utils.action_journal import ActionEvent, ActionJournal, list_journal_runs, read_events
from je_auto_control.utils.codegen.candidate_models import CandidateError
from je_auto_control.utils.codegen.journal_import import generate_candidate_from_log
from je_auto_control.utils.executor.action_executor import Executor


@pytest.mark.parametrize('command,argument', [('AC_private_probe', 'password'), ('AC_jwt_encode', 'key')])
def test_resolved_positional_secret_never_reaches_append_or_logs(tmp_path, monkeypatch, caplog, command, argument):
    secret = 'synthetic-credential-echo'
    executor = Executor()
    executor.variables.set('credential', secret)
    # A fixed local function keeps signature binding real, without crypto/device work.
    def private_probe(password):
        return password

    def key_probe(key):
        return key

    executor.event_dict[command] = private_probe if argument == 'password' else key_probe
    executor.event_dict['AC_echo_probe'] = lambda: 'echo ' + secret
    journal = ActionJournal(tmp_path / 'positional.jsonl')
    appended = []
    append = journal.append

    def capture(event):
        appended.append(event.to_dict())
        append(event)

    monkeypatch.setattr(journal, 'append', capture)
    with journal.run(run_id='positional'):
        result = executor.execute_action([[command, ['${credential}']], ['AC_echo_probe']])
    assert list(result.values()) == [secret, 'echo ' + secret]
    assert secret not in json.dumps(appended)
    assert secret not in journal.path.read_text(encoding='utf-8')
    assert secret not in caplog.text


@pytest.mark.parametrize('secret', ['preseeded-private-value', {'nested': ['preseeded-private-value']}, 123456])
def test_sensitive_getter_scrubs_result_without_changing_caller_value(tmp_path, caplog, secret):
    executor = Executor()
    executor.variables.set('password', secret)
    executor.event_dict['AC_echo_probe'] = lambda: 'public' if isinstance(secret, int) else 'preseeded-private-value'
    journal = ActionJournal(tmp_path / 'getter.jsonl')
    with journal.run(run_id='getter'):
        result = executor.execute_action([['AC_get_var', {'name': 'password'}], ['AC_echo_probe']])
    assert list(result.values())[0] == secret
    assert read_events(journal.path)[0].outcome == '***'
    assert 'preseeded-private-value' not in journal.path.read_text(encoding='utf-8')
    assert 'preseeded-private-value' not in caplog.text
    if isinstance(secret, int):
        assert str(secret) not in caplog.text


@pytest.mark.parametrize('value', [123456, '${credential}'])
def test_numeric_sensitive_parameter_is_private_in_outcomes_and_logs(tmp_path, caplog, value):
    executor = Executor()
    executor.variables.set('credential', 123456)
    executor.event_dict['AC_private_probe'] = lambda password: password
    executor.event_dict['AC_echo_probe'] = lambda: 123456
    journal = ActionJournal(tmp_path / 'numeric-parameter.jsonl')
    with journal.run(run_id='numeric-parameter'):
        result = executor.execute_action([
            ['AC_private_probe', {'password': value}], ['AC_echo_probe'],
        ], raise_on_error=True)
    assert list(result.values()) == [123456, 123456]
    assert '123456' not in journal.path.read_text(encoding='utf-8')
    assert '123456' not in caplog.text


def test_dynamic_sensitive_variable_name_cannot_bypass_input_or_result_privacy(tmp_path, monkeypatch):
    executor = Executor()
    executor.variables.set('field', 'password')
    journal = ActionJournal(tmp_path / 'dynamic-name.jsonl')
    appended = []
    append = journal.append

    def capture(event):
        appended.append(event.to_dict())
        append(event)

    monkeypatch.setattr(journal, 'append', capture)
    with journal.run(run_id='dynamic-name'):
        result = executor.execute_action([
            ['AC_set_var', {'name': '${field}', 'value': 'dynamic-private-value'}],
            ['AC_get_var', {'name': '${field}'}],
        ], raise_on_error=True)
    assert list(result.values()) == ['dynamic-private-value', 'dynamic-private-value']
    assert 'dynamic-private-value' not in json.dumps(appended)
    assert all(event.outcome == '***' for event in read_events(journal.path))


def test_observed_loop_step_without_resolved_binding_is_omitted_with_warning(tmp_path):
    executor = Executor()
    journal = ActionJournal(tmp_path / 'loop.jsonl')
    with journal.run(run_id='loop'):
        executor.execute_action([
            ['AC_for_each', {'items': [10, 20], 'var': 'item',
                             'body': [['AC_set_var', {'name': 'result', 'value': '${item}'}]]}],
            ['AC_sleep', {'seconds': 0}],
        ], raise_on_error=True)
    candidate = generate_candidate_from_log(journal.path, run_id='loop')
    assert candidate.actions == [['AC_sleep', {'seconds': 0}]]
    assert any('binding' in warning for warning in candidate.warnings)
    assert sum(row['included'] for row in candidate.manifest['steps']) == 1
    Executor().execute_action(candidate.actions, raise_on_error=True)


@pytest.mark.parametrize('container', [
    ['AC_loop', {'times': 1, 'body': [['AC_sleep', {'seconds': -1}]]}],
    ['AC_parallel', {'branches': [[['AC_sleep', {'seconds': -1}]]]}],
    ['AC_try', {'body': [['AC_sleep', {'seconds': -1}]],
                'catch': [['AC_sleep', {'seconds': -1}]]}],
])
def test_unhandled_contained_failure_cannot_finish_run_ok(tmp_path, container):
    executor = Executor()
    journal = ActionJournal(tmp_path / 'unhandled.jsonl')
    with journal.run(run_id='unhandled'):
        executor.execute_action([container])
    assert list_journal_runs(str(journal.path))[0]['status'] == 'error'
    assert read_events(journal.path)[0].status == 'error'


@pytest.mark.parametrize('command', ['AC_try', 'AC_retry'])
def test_successfully_handled_failure_retains_successful_run(tmp_path, command):
    executor = Executor()
    attempts = []

    def fail_then_succeed():
        attempts.append(True)
        if len(attempts) == 1:
            raise ValueError('controlled failure')

    executor.event_dict['AC_flaky_probe'] = fail_then_succeed
    arguments = {'body': [['AC_flaky_probe']], 'backoff': 0}
    if command == 'AC_try':
        arguments['catch'] = [['AC_flaky_probe']]
    journal = ActionJournal(tmp_path / 'handled.jsonl')
    with journal.run(run_id='handled'):
        executor.execute_action([[command, arguments]], raise_on_error=True)
    assert list_journal_runs(str(journal.path))[0]['status'] == 'ok'
    assert any(event.status == 'error' for event in read_events(journal.path))


@pytest.mark.parametrize('arguments', [{}, None, [0]])
def test_candidate_rejects_invalid_block_arguments_without_dispatch(tmp_path, arguments, monkeypatch):
    start = ActionEvent('invalid', 'step', None, 1, 'AC_sleep', arguments, 1)
    finish = replace(start, sequence=2, status='ok', finished_at=2)
    path = tmp_path / 'invalid.jsonl'
    path.write_text('\n'.join(json.dumps(event.to_dict()) for event in [start, finish]), encoding='utf-8')
    calls = []
    monkeypatch.setattr('time.sleep', lambda *args: calls.append(args))
    with pytest.raises(CandidateError):
        generate_candidate_from_log(path, run_id='invalid')
    assert calls == []
