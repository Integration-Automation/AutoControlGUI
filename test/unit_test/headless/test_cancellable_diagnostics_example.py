"""The example defaults to controlled work; active mode is tested with inert diagnostic data."""
import json

import pytest

from examples import cancellable_diagnostics as example
from je_auto_control.utils.diagnostics.diagnostics import Check, DiagnosticsReport
from je_auto_control.utils.exception.cancellation import current_cancellation_token


def test_default_example_is_controlled_and_never_starts_active_diagnostics(monkeypatch, capsys):
    def forbidden():
        pytest.fail('the default example started active capture checks')

    monkeypatch.setattr(example, 'run_diagnostics', forbidden)
    assert example.main([]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data['mode'] == 'demo' and data['status'] == 'cancelled'
    assert [value['completed'] for value in data['progress']] == [0]
    assert current_cancellation_token() is None


def test_active_example_binds_the_sdk_token_and_prints_the_existing_report(monkeypatch, capsys):
    def controlled():
        assert current_cancellation_token() is not None
        return DiagnosticsReport([Check('controlled', True, 'info', 'controlled')])

    monkeypatch.setattr(example, 'run_diagnostics', controlled)
    assert example.main(['--active']) == 0
    data = json.loads(capsys.readouterr().out)
    assert data['mode'] == 'active' and data['status'] == 'completed' and data['report']['count'] == 1
    assert current_cancellation_token() is None


@pytest.mark.parametrize('interval', ['-1', 'nan', 'inf', '1e300'])
def test_example_rejects_invalid_stop_intervals_before_any_provider_runs(interval):
    with pytest.raises(SystemExit) as caught:
        example.main(['--active', '--cancel-after', interval])
    assert caught.value.code == 2
