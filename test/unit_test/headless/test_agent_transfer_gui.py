"""Transfer Actions require explicit consent and reject stale background observations."""
import json
from types import SimpleNamespace

import pytest


@pytest.fixture
def tab():
    pytest.importorskip('PySide6')
    from PySide6.QtWidgets import QApplication
    from je_auto_control.gui.agent_tasks_tab import AgentTasksTab
    import shiboken6
    app = QApplication.instance() or QApplication([])
    widget = AgentTasksTab()
    try:
        yield widget
    finally:
        widget.close()
        shiboken6.delete(widget)
        app.processEvents()


def transfer_view(tab):
    from PySide6.QtWidgets import QWidget
    view = tab.findChild(QWidget, 'agent_transfer_view')
    assert view is not None, 'Managed tasks must expose a transfer request/result page'
    return view


@pytest.mark.parametrize('example,operation,fields', [
    ('source', 'review_export', {'source_task', 'selection', 'recipient_policy', 'idempotency_key'}),
    ('destination', 'review_import', {'source_host', 'export_id', 'target', 'directory', 'idempotency_key'}),
    ('evidence', 'review_evidence', {'source_task', 'task_id', 'recipient_policy', 'idempotency_key'}),
])
def test_examples_prepare_explicit_source_destination_and_grant_selection(tab, monkeypatch, example, operation, fields):
    from PySide6.QtWidgets import QPushButton
    view = transfer_view(tab)
    monkeypatch.setattr(view._controller, 'submit', lambda *_a, **_k: pytest.fail('Examples cannot dispatch'))
    actions = dict(tab.menu_actions())
    actions['agent_transfer_example_' + example]()
    assert view._operation.currentData() == operation
    request = json.loads(view._request.toPlainText())
    assert set(request) == fields and request['idempotency_key'] == '<idempotency-key>'
    assert tab._pages.currentWidget() is view and tab.findChildren(QPushButton) == []
    tab.retranslate()
    assert json.loads(view._request.toPlainText()) == request


def submit_capture(view, monkeypatch):
    calls = []
    handle = SimpleNamespace(task_id=41, outcome=None, finished=SimpleNamespace(connect=lambda _slot: None))
    monkeypatch.setattr(view._controller, 'submit', lambda work, **_kw: calls.append(work) or handle)
    return calls, handle


@pytest.mark.parametrize('change', ['none', 'operation', 'request', 'task', 'close', 'away_back'])
def test_late_results_cannot_replace_changed_selection_or_closed_view(tab, monkeypatch, change):
    from je_auto_control.gui.task_controller import TaskOutcome
    view = transfer_view(tab)
    calls, _handle = submit_capture(view, monkeypatch)
    view._operation.setCurrentIndex(view._operation.findData('list_exports'))
    view._request.setPlainText('{"source_task":"selected-source"}')
    dict(tab.menu_actions())['agent_transfer_apply']()
    assert len(calls) == 1
    assert calls[0].args == ('list_exports', {'source_task': 'selected-source'})
    if change == 'operation':
        view._operation.setCurrentIndex(view._operation.findData('list_imports'))
    elif change == 'request':
        view._request.setPlainText('{}')
    elif change == 'task':
        tab._task_id.setText('another-task')
    elif change == 'close':
        tab.close()
    elif change == 'away_back':
        original = view._request.toPlainText()
        view._request.setPlainText('{}')
        view._request.setPlainText(original)
    view._completed(TaskOutcome(41, 'ok', {'exports': []}))
    expected = {'exports': []} if change == 'none' else None
    assert (json.loads(view._result.toPlainText()) if view._result.toPlainText() else None) == expected


def test_review_only_prepares_approval_after_an_explicit_action_preserving_key_and_host(tab, monkeypatch):
    from je_auto_control.gui.task_controller import TaskOutcome
    view = transfer_view(tab)
    calls, handle = submit_capture(view, monkeypatch)
    request = {'host': 'registered-source', 'source_task': 'source', 'selection': [],
               'recipient_policy': 'caller', 'idempotency_key': 'same-key'}
    view._request.setPlainText(json.dumps(request))
    actions = dict(tab.menu_actions())
    actions['agent_transfer_apply']()
    view._completed(TaskOutcome(41, 'ok', {'review': 'a' * 64, 'approval_required': True}))
    assert view._operation.currentData() == 'review_export' and len(calls) == 1
    assert json.loads(view._request.toPlainText()) == request
    actions['agent_transfer_prepare_approval']()
    assert view._operation.currentData() == 'create_export'
    prepared = json.loads(view._request.toPlainText())
    assert prepared == {'host': 'registered-source', 'review': 'a' * 64, 'idempotency_key': 'same-key', 'note': ''}
    actions['agent_transfer_apply']()
    assert len(calls) == 1, 'An empty approval note cannot be sent by the GUI'
    prepared['note'] = 'Reviewed this exact source grant'
    view._request.setPlainText(json.dumps(prepared))
    handle.outcome = 'finished'
    actions['agent_transfer_apply']()
    assert len(calls) == 2 and calls[1].args == ('create_export', prepared)


@pytest.mark.parametrize('language', ['english', 'traditional_chinese', 'simplified_chinese', 'japanese'])
def test_transfer_actions_and_operations_are_explicitly_translated_in_all_locales(tab, language):
    import importlib
    from je_auto_control.utils.agent_runtime.transfer_operations import OPERATIONS
    module = importlib.import_module('je_auto_control.gui.language_wrapper.' + language)
    words = getattr(module, language + '_word_dict')
    keys = {'agent_page_transfers', 'agent_transfer_operation', 'agent_transfer_request', 'agent_transfer_result',
            'agent_transfer_notice', 'agent_transfer_apply', 'agent_transfer_prepare_approval',
            'agent_transfer_example_source', 'agent_transfer_example_destination', 'agent_transfer_example_evidence',
            'agent_transfer_note_required', 'agent_transfer_review_required'}
    keys.update('agent_transfer_op_' + operation for operation in OPERATIONS)
    assert all(words.get(key) and words[key] != key for key in keys)
    view = transfer_view(tab)
    assert tuple(view._operation.itemData(i) for i in range(view._operation.count())) == OPERATIONS


@pytest.mark.parametrize('note', ['', '   ', None, [], 123])
def test_create_rejects_missing_blank_or_nontext_approval_before_dispatch(tab, monkeypatch, note):
    view = transfer_view(tab)
    calls, _handle = submit_capture(view, monkeypatch)
    view._operation.setCurrentIndex(view._operation.findData('create_evidence'))
    view._request.setPlainText(json.dumps({'review': 'a' * 64, 'idempotency_key': 'key', 'note': note}))
    dict(tab.menu_actions())['agent_transfer_apply']()
    assert calls == [] and view._status.text()


def test_closed_transfer_gui_leaves_the_actual_accepted_import_owned_by_the_service(tab, tmp_path, monkeypatch):
    from pathlib import Path
    from threading import Event
    import time
    from PySide6.QtWidgets import QApplication
    from headless.test_agent_transfer_import import import_hosts
    from headless.test_agent_transfer_import_lifecycle import wait_import
    from headless.test_agent_transfer_peer_security import post
    from je_auto_control.utils.agent_runtime import transfer_import_files
    app = QApplication.instance()
    with import_hosts(tmp_path, monkeypatch) as (host, server, exported, body, token, root, _actor):
        entered, release = Event(), Event()
        receive = transfer_import_files.receive_chunks
        def paused(*args):
            entered.set()
            assert release.wait(10)
            return receive(*args)
        monkeypatch.setattr('je_auto_control.utils.agent_runtime.transfer_import.receive_chunks', paused)
        connection = tmp_path / 'owned-gui-connection.json'
        connection.write_text(json.dumps({'url': server.base_url, 'token': token}), encoding='utf-8')
        monkeypatch.setattr('je_auto_control.utils.agent_runtime.client.default_connection_path', lambda: connection)
        status, reviewed = post(server, '/agent/transfer', {'operation': 'review_import', 'request': {
            'source_host': 'source', 'export_id': exported['export_id'], 'target': 'import-files',
            'directory': str(root / 'gui-received'), 'idempotency_key': 'gui-owned-import'}}, token=token)
        assert status == 200, reviewed
        view = transfer_view(tab)
        view._operation.setCurrentIndex(view._operation.findData('create_import'))
        view._request.setPlainText(json.dumps({'review': reviewed['review'],
            'note': 'Reviewed source, destination and immutable manifest', 'idempotency_key': 'gui-owned-import'}))
        try:
            dict(tab.menu_actions())['agent_transfer_apply']()
            deadline = time.monotonic() + 5
            while not view._result.toPlainText():
                app.processEvents()
                assert time.monotonic() < deadline, view._status.text()
                time.sleep(0.01)
            created = json.loads(view._result.toPlainText())
            identifier = created['import']['import_id']
            assert entered.wait(5)
            with host.runtime.store.connection() as database:
                before = host.runtime.transfers.source.records.find(database, identifier)
            tab.close()
            assert host.status()['running'] is True
            release.set()
            current = wait_import(server, token, identifier)
            assert current['state'] == 'published', current
            assert (Path(current['files_directory']) / 'report.txt').read_bytes() == body
            with host.runtime.store.connection() as database:
                after = host.runtime.transfers.source.records.find(database, identifier)
            assert before['scope'] == after['scope'] and before['expires'] == after['expires']
            assert view._result.toPlainText() == '' and host.runtime.list() == []
        finally:
            release.set()
            deadline = time.monotonic() + 5
            while view._controller.active_count:
                app.processEvents()
                assert time.monotonic() < deadline
                time.sleep(0.01)
