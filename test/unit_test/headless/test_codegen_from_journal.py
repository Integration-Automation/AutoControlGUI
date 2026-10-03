"""Candidate generation preserves observed provenance without executing a run."""
import ast
import json
from dataclasses import replace

import pytest

from je_auto_control.utils.action_journal.events import ActionEvent


class Events:
    def __init__(self):
        self.rows, self.sequences = [], {}

    def append(self, event):
        sequence = self.sequences.get(event.run_id, 0) + 1
        self.sequences[event.run_id] = sequence
        event = replace(event, sequence=sequence)
        self.rows.append(event.to_dict())
        return event

    def start(self, command, arguments=None, *, run='selected', parent=None, **metadata):
        return self.append(ActionEvent(run, f'{run}-{len(self.rows)}', parent, 1, command, arguments,
                                       started_at=1, **metadata))

    def finish(self, event, status='ok'):
        return self.append(replace(event, finished_at=2, status=status))

    def write(self, path):
        path.write_text(''.join(json.dumps(row) + '\n' for row in self.rows), encoding='utf-8')
        return path


def generate(path, **kwargs):
    from je_auto_control.utils.codegen.journal_import import generate_candidate_from_log
    return generate_candidate_from_log(path, run_id='selected', **kwargs)


def test_run_filter_and_provenance(tmp_path):
    events = Events()
    other = events.start('AC_sleep', {'seconds': 900}, run='other')
    events.finish(other)
    root = events.start('AC_execute_journaled')
    leaf = events.start('AC_sleep', {'seconds': 0}, parent=root.step_id, source='original.json', source_index=4)
    events.finish(leaf)
    events.finish(root)
    candidate = generate(events.write(tmp_path / 'runs.jsonl'))
    selected_run = 'selected'
    assert candidate.manifest['run_id'] == selected_run
    assert candidate.actions == [['AC_sleep', {'seconds': 0}]]
    assert candidate.manifest['steps'][1]['step_id'] == leaf.step_id
    assert candidate.manifest['steps'][1]['parent_id'] == root.step_id
    assert candidate.manifest['steps'][1]['source_index'] == 4
    assert '900' not in candidate.code
    ast.parse(candidate.code)


def test_observed_branch_is_labelled(tmp_path):
    events = Events()
    branch = events.start('AC_if_var', {'name': 'choice', 'then': [['AC_sleep', {'seconds': 0}]],
                                       'else': [['AC_sleep', {'seconds': 900}]]})
    leaf = events.start('AC_sleep', {'seconds': 0}, parent=branch.step_id)
    events.finish(leaf)
    events.finish(branch)
    candidate = generate(events.write(tmp_path / 'branch.jsonl'))
    assert candidate.observed_path_only is True
    assert candidate.actions == [['AC_sleep', {'seconds': 0}]]
    assert 'observed' in candidate.code.lower() and candidate.warnings


def test_secret_reference_survives_codegen(tmp_path):
    events = Events()
    leaf = events.start('AC_write', {'write_string': '${secrets.PASSWORD}', 'secret': True})
    events.finish(leaf)
    candidate = generate(events.write(tmp_path / 'reference.jsonl'))
    assert '${secrets.PASSWORD}' in candidate.code
    assert candidate.actions[0][1]['write_string'] == '${secrets.PASSWORD}'


def test_generation_has_no_device_effect(tmp_path, monkeypatch):
    from je_auto_control.utils.executor.action_executor import executor
    device_calls = []
    monkeypatch.setitem(executor.event_dict, 'AC_set_mouse_position', lambda *args, **kwargs: device_calls.append(args))
    events = Events()
    leaf = events.start('AC_set_mouse_position', {'x': 1, 'y': 2})
    events.finish(leaf)
    candidate = generate(events.write(tmp_path / 'device.jsonl'))
    assert candidate.actions
    assert device_calls == []


def test_incomplete_masked_and_failed_steps_are_not_replayed(tmp_path):
    events = Events()
    good = events.start('AC_sleep', {'seconds': 0})
    events.finish(good)
    masked = events.start('AC_write', {'write_string': '***', 'secret': True}, replayable=False,
                           replay_reasons=('literal secret masked',))
    events.finish(masked)
    failed = events.start('AC_sleep', {'seconds': 10})
    events.finish(failed, 'error')
    events.start('AC_sleep', {'seconds': 20})
    candidate = generate(events.write(tmp_path / 'partial.jsonl'))
    assert candidate.actions == [['AC_sleep', {'seconds': 0}]]
    assert candidate.observed_path_only is True
    assert len(candidate.warnings) >= 3
    assert len(candidate.manifest['steps']) == 4


def test_parallel_observations_are_flattened_with_an_explicit_warning(tmp_path):
    events = Events()
    parent = events.start('AC_parallel', {'branches': [[['AC_sleep', {'seconds': 0}]],
                                                     [['AC_sleep', {'seconds': 1}]]]})
    one = events.start('AC_sleep', {'seconds': 0}, parent=parent.step_id)
    two = events.start('AC_sleep', {'seconds': 1}, parent=parent.step_id)
    events.finish(two)
    events.finish(one)
    events.finish(parent)
    candidate = generate(events.write(tmp_path / 'parallel.jsonl'))
    assert candidate.actions == [['AC_sleep', {'seconds': 0}], ['AC_sleep', {'seconds': 1}]]
    assert candidate.observed_path_only is True
    assert any('parallel' in warning.lower() for warning in candidate.warnings)


def test_malicious_argument_is_only_source_data(tmp_path):
    marker = tmp_path / 'executed'
    payload = f"__import__('pathlib').Path({str(marker)!r}).write_text('bad')"
    events = Events()
    leaf = events.start('AC_write', {'write_string': payload})
    events.finish(leaf)
    candidate = generate(events.write(tmp_path / 'data.jsonl'))
    ast.parse(candidate.code)
    assert not marker.exists()
    assert candidate.actions[0][1]['write_string'] == payload


def test_unknown_schema_is_rejected_before_codegen(tmp_path):
    from je_auto_control.utils.action_journal.events import JournalError
    events = Events()
    leaf = events.start('AC_sleep', {'seconds': 0})
    events.finish(leaf)
    events.rows[0]['schema_version'] = 99
    with pytest.raises(JournalError):
        generate(events.write(tmp_path / 'future.jsonl'))


def test_missing_required_argument_is_rejected_before_source_generation(tmp_path):
    from je_auto_control.utils.codegen.candidate_models import CandidateError
    events = Events()
    step = events.start('AC_set_mouse_position', {'x': 1})
    events.finish(step)
    with pytest.raises(CandidateError):
        generate(events.write(tmp_path / 'invalid-arguments.jsonl'))


def test_installed_plugin_command_is_validated_without_running_it(tmp_path, monkeypatch):
    from je_auto_control.utils.executor.action_executor import executor
    calls = []
    monkeypatch.setitem(executor.event_dict, 'AC_candidate_fixture_plugin', lambda value: calls.append(value))
    events = Events()
    step = events.start('AC_candidate_fixture_plugin', {'value': 'data'})
    events.finish(step)
    candidate = generate(events.write(tmp_path / 'plugin.jsonl'))
    assert candidate.actions == [['AC_candidate_fixture_plugin', {'value': 'data'}]]
    assert calls == []


def test_retry_manifest_retains_failed_and_completed_observed_attempts(tmp_path):
    events = Events()
    retry = events.start('AC_retry', {'body': [['AC_sleep', {'seconds': 0}]], 'times': 2})
    failed = events.start('AC_sleep', {'seconds': 0}, parent=retry.step_id, source_index=0)
    events.finish(failed, 'error')
    good = events.start('AC_sleep', {'seconds': 0}, parent=retry.step_id, source_index=0)
    events.finish(good)
    events.finish(retry)
    candidate = generate(events.write(tmp_path / 'retry.jsonl'))
    attempts = candidate.manifest['steps'][1:]
    assert [row['observed_attempt'] for row in attempts] == [1, 2]
    assert [row['status'] for row in attempts] == ['error', 'ok']
    assert candidate.actions == [['AC_sleep', {'seconds': 0}]]


def test_journal_candidate_delivery_surfaces_and_export(tmp_path):
    import je_auto_control as ac
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    assert 'generate_journal_candidate' in ac.__all__
    assert 'AC_generate_journal_candidate' in executor.known_commands()
    assert 'AC_generate_journal_candidate' in COMMAND_SPECS
    assert 'ac_generate_journal_candidate' in {tool.name for tool in build_default_tool_registry()}
    events = Events()
    step = events.start('AC_sleep', {'seconds': 0})
    events.finish(step)
    journal = events.write(tmp_path / 'surface.jsonl')
    output = tmp_path / 'candidate.py'
    artifact = ac.generate_journal_candidate(str(journal), 'selected', output_path=str(output))
    assert output.read_text(encoding='utf-8') == artifact['code']
    assert json.loads(output.with_suffix('.manifest.json').read_text(encoding='utf-8')) == artifact['manifest']
    assert json.loads(output.with_suffix('.actions.json').read_text(encoding='utf-8')) == artifact['actions']


def test_cli_from_log_filters_run_and_exports_source_and_manifest(tmp_path, capsys):
    from je_auto_control import cli
    events = Events()
    step = events.start('AC_sleep', {'seconds': 0})
    events.finish(step)
    source = events.write(tmp_path / 'cli.jsonl')
    output = tmp_path / 'test_candidate.py'
    assert cli.main(['codegen', '--from-log', str(source), '--run-id', 'selected', '-o', str(output)]) == 0
    assert output.is_file() and output.with_suffix('.manifest.json').is_file()
    ast.parse(output.read_text(encoding='utf-8'))


def test_candidate_export_cannot_replace_its_source_journal(tmp_path):
    from je_auto_control.utils.codegen.candidate_models import CandidateError
    from je_auto_control.utils.codegen.journal_api import generate_journal_candidate
    events = Events()
    step = events.start('AC_sleep', {'seconds': 0})
    events.finish(step)
    source = events.write(tmp_path / 'preserved.jsonl')
    original = source.read_bytes()
    with pytest.raises(CandidateError):
        generate_journal_candidate(str(source), 'selected', output_path=str(source))
    assert source.read_bytes() == original


def test_non_replayable_reason_does_not_echo_a_secret_literal(tmp_path):
    events = Events()
    good = events.start('AC_sleep', {'seconds': 0})
    events.finish(good)
    hidden = events.start('AC_write', {'write_string': 'private-literal', 'secret': True}, replayable=False,
                           replay_reasons=('masked private-literal',))
    events.finish(hidden)
    candidate = generate(events.write(tmp_path / 'private.jsonl'))
    assert 'private-literal' not in json.dumps(candidate.to_dict())
