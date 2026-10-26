"""Passive installed-contract metadata cannot start services, contact peers or establish live authority."""
import pytest

from je_auto_control.utils.diagnostics import diagnostics
from je_auto_control.utils.agent_runtime.transfer_models import TransferManifest, MAX_MANIFEST_BYTES, MAX_TRANSFER_BYTES
from je_auto_control.utils.agent_runtime.transfer_operations import OPERATIONS


def test_transfer_contract_probe_is_registered_and_does_not_touch_a_service_or_remote_host(monkeypatch, tmp_path):
    check = getattr(diagnostics, '_check_agent_transfer_contract', None)
    assert callable(check), 'Diagnostics must distinguish an installed transfer contract from live authority'
    assert check in diagnostics._ALL_CHECKS
    def forbidden(*_args, **_kwargs):
        pytest.fail('A passive installed-contract probe cannot start or contact any service')
    monkeypatch.setattr('je_auto_control.utils.agent_runtime.api.start_agent_runtime', forbidden)
    monkeypatch.setattr('je_auto_control.utils.agent_runtime.client.AgentRuntimeClient.call', forbidden)
    monkeypatch.setattr('je_auto_control.utils.agent_runtime.transfer_protocol.AgentTransfers.control', forbidden)
    monkeypatch.setattr('je_auto_control.utils.agent_runtime.transport.request_json', forbidden)
    before = set(tmp_path.rglob('*'))
    result = check()
    assert result.name == 'agent_transfer_contract' and result.ok and result.severity == 'info'
    assert result.extra == {'contract': TransferManifest.contract, 'operations': list(OPERATIONS),
        'max_manifest_bytes': MAX_MANIFEST_BYTES, 'max_transfer_bytes': MAX_TRANSFER_BYTES,
        'max_files': 500, 'state': 'contract_only', 'authority_granted': False,
        'remote_verified': False, 'native_verified': False}
    result.extra['operations'].clear()
    assert check().extra['operations'] == list(OPERATIONS)
    assert set(tmp_path.rglob('*')) == before


@pytest.mark.parametrize('surface', ['python', 'executor'])
def test_existing_shared_diagnostics_surface_reports_only_contract_availability(monkeypatch, surface):
    check = getattr(diagnostics, '_check_agent_transfer_contract', None)
    assert callable(check), 'The installed transfer contract needs passive diagnostics'
    monkeypatch.setattr(diagnostics, '_ALL_CHECKS', (check,))
    if surface == 'python':
        import je_auto_control as ac
        report = ac.run_diagnostics().to_dict()
    else:
        from je_auto_control.utils.tool_use_schema import run_tool_call
        report = run_tool_call('AC_diagnose', {})
    assert report['count'] == 1
    extra = report['checks'][0]['extra']
    assert extra['state'] == 'contract_only' and extra['authority_granted'] is False
    assert extra['remote_verified'] is False and extra['native_verified'] is False
