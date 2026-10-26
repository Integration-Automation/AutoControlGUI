"""Actual configured host credential books stay private without loading or rewriting user configuration."""
from pathlib import Path

import pytest

from headless.test_agent_transfer_private_sources import completed_file
from headless.test_agent_transfer_source import completed_source, create_for, review_for
from je_auto_control.utils.admin import admin_client
from je_auto_control.utils.agent_runtime import AgentTaskError, transfer_files


def host_book(path):
    client = admin_client.AdminConsoleClient(persist_path=path)
    client.add_host('source', 'http://127.0.0.1:9', 'owned-fixture-credential')
    return client


@pytest.mark.parametrize('initialized', [False, True])
def test_actual_host_book_is_private_before_byte_open_without_loading_configuration(tmp_path, monkeypatch, initialized):
    private = tmp_path / 'actual-hosts.json'
    client = host_book(private) if initialized else None
    if not initialized:
        private.write_bytes(b'owned malformed fixture; source exclusion must not parse or quarantine it')
    before = private.read_bytes()
    monkeypatch.setattr(admin_client, '_default_console', client)
    monkeypatch.setattr(admin_client, 'default_admin_hosts_path', lambda: private)
    def forbidden_load(*_args, **_kwargs):
        raise AssertionError('source authority must not initialize or reload the host book')
    monkeypatch.setattr(admin_client.AdminConsoleClient, '_load', forbidden_load)
    with completed_source(tmp_path) as (runtime, _initial, _output, _body, _users):
        task = completed_file(runtime, tmp_path, private)
        original = transfer_files.os.open
        def confined(value, *args, **kwargs):
            if Path(value).resolve() == private.resolve():
                raise AssertionError('private host credential descriptor reached byte access')
            return original(value, *args, **kwargs)
        monkeypatch.setattr(transfer_files.os, 'open', confined)
        with pytest.raises(AgentTaskError, match='private'):
            review_for(runtime, task)
    assert private.read_bytes() == before
    assert not list(tmp_path.glob('actual-hosts.json.*'))


@pytest.mark.parametrize('boundary', ['export', 'chunk', 'retry'])
def test_current_registry_reclassification_invalidates_an_older_approved_artifact(tmp_path, monkeypatch, boundary):
    first = host_book(tmp_path / 'first-hosts.json')
    second = host_book(tmp_path / 'second-hosts.json')
    monkeypatch.setattr(admin_client, '_default_console', first)
    with completed_source(tmp_path) as (runtime, _initial, _output, _body, _users):
        task = completed_file(runtime, tmp_path, second.persist_path)
        review = review_for(runtime, task)
        exported = create_for(runtime, review)
        monkeypatch.setattr(admin_client, '_default_console', second)
        with pytest.raises(AgentTaskError, match='private'):
            if boundary == 'retry':
                create_for(runtime, review)
            else:
                request = {'export_id': exported['export_id']}
                if boundary == 'chunk':
                    request['sha256'] = exported['manifest']['files'][0]['chunks'][0]
                runtime.transfers.peer(boundary, request)


def test_ordinary_output_with_the_actual_books_basename_is_not_reserved(tmp_path, monkeypatch):
    client = host_book(tmp_path / 'private' / 'hosts.json')
    monkeypatch.setattr(admin_client, '_default_console', client)
    with completed_source(tmp_path) as (runtime, _initial, _output, _body, _users):
        output = tmp_path / 'hosts.json'
        output.write_bytes(b'explicit ordinary user artifact')
        task = completed_file(runtime, tmp_path, output)
        assert create_for(runtime, review_for(runtime, task))['state'] == 'active'
