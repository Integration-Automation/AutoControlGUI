"""Actual host-profile changes and registered transfer reads cannot invert runtime and SQLite lock order."""
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from threading import Event

from headless.test_agent_transfer_registered import registered_source
from headless.test_agent_transfer_peer_security import source_server
from je_auto_control.utils.agent_runtime import AgentRuntime
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope


def prove_order(runtime, monkeypatch, lookup, target, writer_context, changing_context):
    writer_entered, profile_entered, writer_finished = Event(), Event(), Event()
    original = runtime.target_profiles._toggle
    def toggle(name, enabled):
        profile_entered.set()
        return original(name, enabled)
    monkeypatch.setattr(runtime.target_profiles, '_toggle', toggle)
    def writer():
        with runtime.store.connection(write=True) as connection:
            writer_entered.set()
            assert profile_entered.wait(3)
            lookup(connection)
            writer_finished.set()
    with ThreadPoolExecutor(max_workers=2) as workers:
        writing = workers.submit(writer_context.run, writer)
        assert writer_entered.wait(3)
        changing = workers.submit(changing_context.run, runtime.target_profiles.control, 'disable', {'name': target})
        assert writer_finished.wait(1), 'transfer authority check inverted runtime-mutex/SQLite-writer order'
        writing.result(timeout=3)
        assert changing.result(timeout=3)['enabled'] is False


def test_registered_binding_does_not_wait_for_runtime_mutex_while_owning_the_writer(tmp_path, monkeypatch):
    with registered_source(tmp_path, monkeypatch):
        runtime = AgentRuntime(tmp_path / 'coordinator.sqlite3', targets={})
        try:
            runtime.target_profiles.control('register', {'name': 'files', 'kind': 'files',
                'allowed_tools': ['AC_workflow_manifest'], 'roots': [str(tmp_path)], 'apps': [], 'settings': {}})
            controller = runtime.transfers
            def lookup(_connection):
                assert len(runtime.batches.transfer_binding('source')) == 64
                assert runtime.transfers is controller
            prove_order(runtime, monkeypatch, lookup, 'files', copy_context(), copy_context())
        finally:
            runtime.close()


def test_source_retirement_proof_does_not_invert_profile_toggle_and_writer(tmp_path, monkeypatch):
    with source_server(tmp_path, named=True) as (server, task, _body, users):
        runtime = server._agent_runtime
        controller = runtime.transfers
        owner = runtime.store.get(task)['owner']
        with authorization_scope(AuthorizationContext(**owner)):
            writer_context = copy_context()
        with authorization_scope(AuthorizationContext('reviewer', 'admin', store_path=str(users.path))):
            changing_context = copy_context()
        def lookup(connection):
            assert controller.source.host.context(task, owner, connection=connection)['row']['state'] == 'succeeded'
        prove_order(runtime, monkeypatch, lookup, 'local-files', writer_context, changing_context)
