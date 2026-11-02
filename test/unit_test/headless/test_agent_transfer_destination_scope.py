"""Destination imports use actual immutable profiles and live origin ceilings without synthetic tasks."""
from pathlib import Path

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.origin_policy import OriginWitness, origin_scope


@pytest.fixture
def destination(tmp_path):
    runtime = AgentRuntime(tmp_path / 'destination.sqlite3', targets={})
    root = tmp_path / 'output'
    root.mkdir()
    runtime.target_profiles.control('register', {'name': 'files', 'kind': 'files',
        'allowed_tools': ['AC_workflow_manifest'], 'roots': [str(root)], 'apps': [], 'settings': {}})
    try:
        yield runtime, root
    finally:
        runtime.close()


def scope(runtime, directory, **options):
    return runtime.transfers.source.host.destination_context('files', str(directory), **options)


def test_review_pins_the_real_profile_without_creating_output_or_tasks(destination):
    runtime, root = destination
    reviewed = scope(runtime, root / 'new')
    assert reviewed['directory'] == str((root / 'new').resolve())
    assert reviewed['profile'] == {'name': 'files', 'digest': runtime.target_profiles.control(
        'get', {'name': 'files'})['digest']}
    assert reviewed['origins'] == []
    assert not (root / 'new').exists()
    assert runtime.list() == []
    assert scope(runtime, root / 'new', reviewed=reviewed) == reviewed


def test_outside_profile_is_refused_even_when_the_directory_exists(destination, tmp_path):
    runtime, _root = destination
    with pytest.raises(AgentTaskError, match='scope|outside|root'):
        scope(runtime, tmp_path)


def test_disable_is_read_from_the_owning_transaction_not_a_stale_cache(destination):
    runtime, root = destination
    reviewed = scope(runtime, root / 'new')
    with runtime.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_target_controls SET enabled=0 WHERE name='files'")
        with pytest.raises(AgentTaskError, match='disabled|profile'):
            scope(runtime, root / 'new', reviewed=reviewed, connection=connection)


@pytest.mark.parametrize('change', ['digest', 'config', 'missing'])
def test_durable_profile_integrity_is_required(destination, change):
    runtime, root = destination
    with runtime.store.connection(write=True) as connection:
        if change == 'missing':
            connection.execute("DELETE FROM agent_target_profiles WHERE name='files'")
        else:
            statement = {'digest': "UPDATE agent_target_profiles SET digest='changed' WHERE name='files'",
                         'config': "UPDATE agent_target_profiles SET config='{}' WHERE name='files'"}[change]
            connection.execute(statement)
        with pytest.raises(AgentTaskError, match='profile|integrity'):
            scope(runtime, root / 'new', connection=connection)


def test_destination_path_cannot_change_after_review(destination):
    runtime, root = destination
    reviewed = scope(runtime, root / 'first')
    with pytest.raises(AgentTaskError, match='changed|review'):
        scope(runtime, root / 'second', reviewed=reviewed)


def test_live_origin_ceiling_is_retained_after_the_request_scope_exits(destination, monkeypatch, tmp_path):
    from je_auto_control.utils.agent_runtime import origin_policy
    monkeypatch.setattr(origin_policy, '_directory', lambda: tmp_path / 'origins')
    runtime, root = destination
    allowed = root / 'allowed'
    allowed.mkdir()
    witness = OriginWitness((allowed,))
    with origin_scope(witness.identifier):
        reviewed = scope(runtime, allowed / 'received')
        with pytest.raises(AgentTaskError, match='scope|outside|root'):
            scope(runtime, root / 'elsewhere')
    assert reviewed['origins'] == [witness.identifier]
    assert scope(runtime, allowed / 'received', reviewed=reviewed) == reviewed
    witness.update((allowed / 'narrowed',))
    with pytest.raises(AgentTaskError, match='scope|outside|root'):
        scope(runtime, allowed / 'received', reviewed=reviewed)


def test_revoked_origin_cannot_be_replaced_by_an_unrestricted_request(destination, monkeypatch, tmp_path):
    from je_auto_control.utils.agent_runtime import origin_policy
    monkeypatch.setattr(origin_policy, '_directory', lambda: tmp_path / 'origins')
    runtime, root = destination
    witness = OriginWitness((root,))
    with origin_scope(witness.identifier):
        reviewed = scope(runtime, root / 'new')
    witness.revoke()
    with pytest.raises(AgentTaskError, match='revoked|review'):
        scope(runtime, root / 'new', reviewed=reviewed)


def test_new_request_origin_can_only_narrow_a_retained_review(destination, monkeypatch, tmp_path):
    from je_auto_control.utils.agent_runtime import origin_policy
    monkeypatch.setattr(origin_policy, '_directory', lambda: tmp_path / 'origins')
    runtime, root = destination
    reviewed = scope(runtime, root / 'new')
    witness = OriginWitness((root / 'elsewhere',))
    with origin_scope(witness.identifier), pytest.raises(AgentTaskError, match='scope|outside|root'):
        scope(runtime, root / 'new', reviewed=reviewed)


@pytest.mark.parametrize('target', ['local-files', 'missing'])
def test_unmanaged_or_missing_target_never_grants_import_authority(destination, target):
    runtime, root = destination
    with pytest.raises(AgentTaskError, match='profile|target'):
        runtime.transfers.source.host.destination_context(target, str(root / 'new'))


def test_directory_must_be_an_absolute_text_path(destination):
    runtime, _root = destination
    for directory in ('relative', '', None, Path('relative')):
        with pytest.raises(AgentTaskError, match='directory|path'):
            runtime.transfers.source.host.destination_context('files', directory)
