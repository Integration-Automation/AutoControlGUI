"""Structured action journals preserve provenance without persisting secrets."""
import json
import threading

import pytest

from je_auto_control.utils.action_journal import ActionJournal, read_events
from je_auto_control.utils.executor.action_executor import Executor


def test_sequence_contract_normalizes_tuple_input():
    from je_auto_control.utils.action_journal.api import _action_input
    assert _action_input((['AC_sleep', {'seconds': 0}],)) == [['AC_sleep', {'seconds': 0}]]


def test_journal_command_stub_preserves_recursive_json_types():
    from je_auto_control.utils.action_journal import execute_journaled
    from je_auto_control.utils.stubs import collect_signatures, render_pyi
    stub = render_pyi(collect_signatures({'AC_execute_journaled': execute_journaled}))
    assert 'ForwardRef(' not in stub
    assert 'from je_auto_control.utils.action_journal.events import JSONValue' in stub


def test_unfinished_child_keeps_run_incomplete():
    from je_auto_control.utils.action_journal.api import _run_status
    from je_auto_control.utils.action_journal import ActionEvent
    parent = ActionEvent('run', 'parent', None, 1, 'AC_try', None, 1, 3, 'ok')
    child = ActionEvent('run', 'child', 'parent', 2, 'AC_sleep', None, 2)
    assert _run_status([parent, child]) == 'incomplete'


def test_masked_known_secret_input_is_not_replayable(tmp_path, caplog):
    executor = Executor()
    executor.event_dict['AC_private'] = lambda secret: None
    executor.event_dict['AC_echo'] = lambda text: None
    journal = ActionJournal(tmp_path / 'input.jsonl')
    with journal.run(run_id='input'):
        executor.execute_action([['AC_private', {'secret': 'private-value'}],
                                 ['AC_echo', {'text': 'private-value'}]])
    echoed = read_events(journal.path)[1]
    assert echoed.arguments == {'text': '***'}
    assert echoed.replayable is False
    assert 'private-value' not in caplog.text


def test_redaction_precedes_append(tmp_path, monkeypatch):
    journal = ActionJournal(tmp_path / 'actions.jsonl')
    password = 'journal-private-value'
    executor = Executor()
    executor.event_dict['AC_write_secret'] = lambda secret: None
    captured = []
    original = journal.append

    def spy(event):
        captured.append(event.to_dict())
        original(event)

    monkeypatch.setattr(journal, 'append', spy)
    with journal.run(run_id='private-run'):
        executor.execute_action([['AC_write_secret', {'secret': password}]])
    journal_text = journal.path.read_text(encoding='utf-8')
    assert password not in journal_text
    assert password not in json.dumps(captured)


def test_parallel_parent_and_order(tmp_path):
    journal = ActionJournal(tmp_path / 'actions.jsonl')
    executor = Executor()
    barrier = threading.Barrier(2)
    executor.event_dict['AC_wait_pair'] = lambda: barrier.wait(timeout=2)
    run_id = 'parallel-run'
    with journal.run(run_id=run_id):
        executor.execute_action([['AC_parallel', {'branches': [
            [['AC_wait_pair']], [['AC_wait_pair']]]}]])
    events = read_events(journal.path)
    assert all(event.run_id == run_id for event in events)
    parent = next(event for event in events if event.command == 'AC_parallel')
    children = [event for event in events if event.command == 'AC_wait_pair']
    assert len(children) == 2
    assert all(event.parent_id == parent.step_id for event in children)
    assert len({event.step_id for event in children}) == 2
    assert [event.sequence for event in events] == sorted(event.sequence for event in events)


def test_incomplete_step_stays_incomplete(tmp_path):
    journal = ActionJournal(tmp_path / 'actions.jsonl')
    executor = Executor()

    def interrupted():
        raise SystemExit(7)

    executor.event_dict['AC_interrupted'] = interrupted
    with pytest.raises(SystemExit), journal.run(run_id='interrupted-run'):
        executor.execute_action([['AC_interrupted']])
    unfinished = read_events(journal.path)[0]
    assert unfinished.status == 'incomplete'
    assert unfinished.finished_at is None


def test_secret_reference_is_retained_without_its_resolved_value(tmp_path, monkeypatch):
    from je_auto_control.utils.script_vars import interpolate
    password = 'resolved-journal-private-value'
    monkeypatch.setattr(interpolate, '_lookup_secret', lambda name: password)
    journal = ActionJournal(tmp_path / 'actions.jsonl')
    executor = Executor()
    executor.event_dict['AC_write_secret'] = lambda secret: None
    with journal.run(run_id='reference-run'):
        executor.execute_action([['AC_write_secret', {'secret': '${secrets.LOGIN}'}]])
    text = journal.path.read_text(encoding='utf-8')
    assert password not in text
    assert '${secrets.LOGIN}' in text


def test_failed_step_cannot_be_journalled_as_success(tmp_path):
    journal = ActionJournal(tmp_path / 'actions.jsonl')
    executor = Executor()

    def failed():
        raise ValueError('controlled failure')

    executor.event_dict['AC_failed'] = failed
    with journal.run(run_id='failed-run'):
        executor.execute_action([['AC_failed']])
    event = read_events(journal.path)[0]
    assert event.status == 'error'
    assert event.finished_at is not None


def test_serialization_never_calls_an_unknown_result_repr(tmp_path):
    class Unknown:
        def __repr__(self):
            raise AssertionError('journal must not invoke repr')

    # Inspect the serializer directly: the legacy executor's ordinary log
    # formats results independently of this new journal boundary.
    from je_auto_control.utils.action_journal.events import safe_payload
    payload, reasons = safe_payload(Unknown())
    assert payload is None
    assert reasons


def test_resolved_secret_is_removed_from_later_outcomes(tmp_path, monkeypatch, caplog):
    from je_auto_control.utils.script_vars import interpolate
    password = 'private-journal-echo'
    monkeypatch.setattr(interpolate, '_lookup_secret', lambda name: password)
    journal = ActionJournal(tmp_path / 'echo.jsonl')
    executor = Executor()
    executor.event_dict['AC_echo'] = lambda text: text
    with journal.run(run_id='echo-run'):
        executor.execute_action([
            ['AC_set_var', {'name': 'value', 'value': '${secrets.LOGIN}'}],
            ['AC_echo', {'text': '${value}'}],
        ])
    assert password not in journal.path.read_text(encoding='utf-8')
    assert password not in caplog.text


def test_unknown_schema_is_a_framework_error(tmp_path):
    from je_auto_control.utils.exception.exceptions import AutoControlException
    path = tmp_path / 'future.jsonl'
    path.write_text('{"schema_version":99}\n', encoding='utf-8')
    with pytest.raises(AutoControlException):
        read_events(path)


def test_masked_literal_is_explicitly_not_replayable(tmp_path):
    journal = ActionJournal(tmp_path / 'literal.jsonl')
    executor = Executor()
    executor.event_dict['AC_write_secret'] = lambda secret: None
    with journal.run():
        executor.execute_action([['AC_write_secret', {'secret': 'private-literal'}]])
    event = read_events(journal.path)[0]
    assert event.replayable is False
    assert event.replay_reasons


def test_positional_crypto_key_is_masked_before_append(tmp_path, caplog):
    journal = ActionJournal(tmp_path / 'positional.jsonl')
    executor = Executor()
    executor.event_dict['AC_sign_action_file'] = lambda path, key: None
    with journal.run():
        executor.execute_action([['AC_sign_action_file', ['script.json', 'private-positional-key']]])
    assert 'private-positional-key' not in journal.path.read_text(encoding='utf-8')
    assert 'private-positional-key' not in caplog.text


def test_null_start_timestamp_is_rejected():
    from je_auto_control.utils.action_journal import ActionEvent, JournalError
    with pytest.raises(JournalError):
        ActionEvent.from_dict({
            'schema_version': 1, 'run_id': 'run', 'step_id': 'step', 'parent_id': None,
            'sequence': 1, 'command': 'AC_sleep', 'arguments': {'seconds': 0},
            'started_at': None,
        })


def test_journal_api_records_history_and_exposes_safe_read_adapters(tmp_path, monkeypatch):
    import je_auto_control as ac
    from je_auto_control.utils.action_journal import api
    from je_auto_control.utils.run_history.history_store import HistoryStore
    history = HistoryStore()
    monkeypatch.setattr(api, 'default_history_store', history)
    path = tmp_path / 'public.jsonl'
    result = ac.execute_journaled([['AC_set_var', {'name': 'counter', 'value': 1}]], str(path), run_id='public')
    assert result['run_id'] == 'public'
    assert ac.read_action_journal(str(path), run_id='public')[0]['status'] == 'ok'
    assert ac.list_journal_runs(str(path))[0]['run_id'] == 'public'
    record = history.list_runs()[0]
    assert record.status == 'ok'
    assert record.artifact_path == str(path)


def test_journal_commands_and_tools_share_the_same_interfaces():
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
    commands = {'AC_execute_journaled', 'AC_read_action_journal', 'AC_list_journal_runs'}
    assert commands <= set(Executor().known_commands())
    assert commands <= set(COMMAND_SPECS)
    tools = {tool.name: tool for tool in build_default_tool_registry()}
    assert {name.lower() for name in commands} <= set(tools)
    assert tools['ac_execute_journaled'].annotations.read_only is False
    assert tools['ac_execute_journaled'].annotations.destructive is True
    assert tools['ac_execute_journaled'].annotations.idempotent is False
    assert tools['ac_read_action_journal'].input_schema['properties']['path']['format'] == 'path'


def test_environment_recording_is_common_to_the_executor_boundary(tmp_path, monkeypatch):
    path = tmp_path / 'automatic.jsonl'
    monkeypatch.setenv('JE_AUTOCONTROL_ACTION_JOURNAL', str(path))
    Executor().execute_action([['AC_set_var', {'name': 'value', 'value': 1}]])
    assert read_events(path)[0].status == 'ok'


def test_reused_run_id_cannot_corrupt_existing_records(tmp_path):
    from je_auto_control.utils.action_journal import JournalError
    journal = ActionJournal(tmp_path / 'reused.jsonl')
    with journal.run(run_id='same'):
        Executor().execute_action([['AC_set_var', {'name': 'value', 'value': 1}]])
    original = journal.path.read_bytes()
    with pytest.raises(JournalError), journal.run(run_id='same'):
        Executor().execute_action([['AC_set_var', {'name': 'value', 'value': 2}]], raise_on_error=True)
    assert journal.path.read_bytes() == original


def test_loaded_files_retain_source_paths_and_indices(tmp_path):
    first = tmp_path / 'first.json'
    second = tmp_path / 'second.json'
    for path in (first, second):
        path.write_text(json.dumps([['AC_set_var', {'name': 'value', 'value': 1}]]), encoding='utf-8')
    journal = ActionJournal(tmp_path / 'sources.jsonl')
    with journal.run():
        Executor().execute_files([str(first), str(second)])
    events = read_events(journal.path)
    assert [event.source for event in events] == [str(first), str(second)]
    assert [event.source_index for event in events] == [0, 0]


@pytest.mark.parametrize('positional', [False, True])
def test_serialized_nested_actions_are_sanitized_before_the_parent_append(tmp_path, monkeypatch, caplog, positional):
    from je_auto_control.utils.action_journal import api
    from je_auto_control.utils.executor import action_executor
    from je_auto_control.utils.run_history.history_store import HistoryStore
    executor = Executor()
    executor.event_dict['AC_write_secret'] = lambda secret: None
    monkeypatch.setattr(action_executor, 'executor', executor)
    monkeypatch.setattr(api, 'default_history_store', HistoryStore())
    journal = ActionJournal(tmp_path / 'parent.jsonl')
    child = tmp_path / 'child.jsonl'
    actions = json.dumps([['AC_write_secret', {'secret': 'private-serialized-literal'}]])
    arguments = [actions, str(child)] if positional else {'actions': actions, 'path': str(child)}
    with journal.run():
        executor.execute_action([['AC_execute_journaled', arguments]])
    assert 'private-serialized-literal' not in journal.path.read_text(encoding='utf-8')
    assert 'private-serialized-literal' not in child.read_text(encoding='utf-8')
    assert 'private-serialized-literal' not in caplog.text


def test_positional_serialized_actions_retain_the_original_secret_reference(tmp_path, monkeypatch):
    from je_auto_control.utils.action_journal import api
    from je_auto_control.utils.executor import action_executor
    from je_auto_control.utils.run_history.history_store import HistoryStore
    from je_auto_control.utils.script_vars import interpolate
    monkeypatch.setattr(interpolate, '_lookup_secret', lambda name: 'private-positional-resolved')
    executor = Executor()
    executor.event_dict['AC_write_secret'] = lambda secret: None
    monkeypatch.setattr(action_executor, 'executor', executor)
    monkeypatch.setattr(api, 'default_history_store', HistoryStore())
    path = tmp_path / 'reference-child.jsonl'
    actions = json.dumps([['AC_write_secret', {'secret': '${secrets.LOGIN}'}]])
    executor.execute_action([['AC_execute_journaled', [actions, str(path)]]], raise_on_error=True)
    text = path.read_text(encoding='utf-8')
    assert '${secrets.LOGIN}' in text
    assert 'private-positional-resolved' not in text
