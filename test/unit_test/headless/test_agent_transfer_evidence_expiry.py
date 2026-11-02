"""Portable proof expires at its earliest real terminal witness without retiring newer artifact snapshots."""
from types import SimpleNamespace

import pytest

from headless.test_agent_transfer_evidence import (
    evidence_server, evidence_review, evidence_create, evidence_read, actual_binding,
)
from headless.test_agent_transfer_source import create_for, review_for
from headless.test_agent_transfer_source_lineage import recovered_file_node
from je_auto_control.utils.agent_runtime import AgentRuntime, transfer_source, transfer_records
from je_auto_control.utils.agent_runtime import transfer_evidence
from je_auto_control.utils.agent_runtime.file_target import FileTarget


@pytest.mark.parametrize('restart', [False, True])
def test_evidence_expiry_preserves_later_artifact_grant_and_all_user_output(tmp_path, monkeypatch, restart):
    with recovered_file_node(tmp_path, recovery_config={'ancestor_age': 120}) as values:
        runtime, source, child, output, body, _batch = values
        exported = create_for(runtime, review_for(runtime, child))
        with evidence_server(runtime) as server:
            status, created = evidence_create(server, evidence_review(server, source, child))
            assert status == 200, created
        grant = created['evidence']['grant_id']
        expiry = created['evidence']['summary']['expires']
        with runtime.store.connection() as connection:
            original = runtime.store.read_task(connection, source)
            assert original['state'] == 'cancelled' and expiry == original['updated'] + 30 * 86400
            intent = dict(connection.execute('SELECT * FROM agent_transfer_intents WHERE id=?', (grant,)).fetchone())
        assert exported['manifest']['expires'] > expiry + 100
        binding = actual_binding(runtime, source)
        if restart:
            runtime.close()
            runtime = AgentRuntime(runtime.store.path, targets={'local-files': FileTarget()})
            assert runtime._transfers is None
        try:
            with evidence_server(runtime) as server:
                assert evidence_read(server, grant, binding)[0] == 200
            clock = SimpleNamespace(time=lambda: expiry + 1)
            for module in (transfer_evidence, transfer_source, transfer_records):
                monkeypatch.setattr(module, 'time', clock)
            if restart:
                # Reacquire a genuinely cold owner after validating the durable grant, without a listener.
                runtime.close()
                runtime = AgentRuntime(runtime.store.path, targets={'local-files': FileTarget()})
                assert runtime._transfers is None
            else:
                with evidence_server(runtime) as server:
                    assert evidence_read(server, grant, binding)[0] == 409
            runtime.maintain()
            runtime.maintain()
            with runtime.store.connection() as connection:
                assert connection.execute('SELECT 1 FROM agent_transfer_grants WHERE id=?', (grant,)).fetchone() is None
                retained = connection.execute('SELECT * FROM agent_transfer_intents WHERE id=?', (grant,)).fetchone()
                assert dict(retained) == intent
                assert connection.execute('SELECT 1 FROM agent_transfer_revocations WHERE id=?', (grant,)).fetchone()
                artifact = runtime.transfers.source.records.find(connection, exported['export_id'])
                assert artifact['state'] == 'active' and artifact['held'] is True
            assert runtime.transfers.peer('export', {'export_id': exported['export_id']}) == exported['manifest']
            assert output.read_bytes() == body
        finally:
            if restart:
                runtime.close()
