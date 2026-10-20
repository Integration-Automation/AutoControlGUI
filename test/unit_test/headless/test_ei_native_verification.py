"""Native EI evidence must distinguish a teardown fault from an unrelated failed probe."""
import importlib.util
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
READY = 'ei_unref: begin\n'
DONE = 'ei_unref: end\n'


@pytest.fixture
def verifier():
    spec = importlib.util.spec_from_file_location('controlled_ei_verifier', ROOT/'docker/libei_verify.py')
    module = importlib.util.module_from_spec(spec)
    with patch('faulthandler.enable'):
        spec.loader.exec_module(module)
    return module


def completed(code, output='', error=''):
    return subprocess.CompletedProcess(['controlled-child'], code, output, error)


@pytest.mark.parametrize('code', [1, 4, -6, -15])
def test_unrelated_child_failure_cannot_claim_that_teardown_no_longer_crashes(verifier, monkeypatch, code):
    monkeypatch.setattr(subprocess, 'run', lambda *_args, **_kwargs: completed(code, error='controlled failure'))
    with pytest.raises(AssertionError, match='unexpected'):
        verifier._check_unref_sentinel('/controlled/eis')


def test_fault_before_unref_is_not_classified_as_a_teardown_bug(verifier, monkeypatch):
    monkeypatch.setattr(subprocess, 'run', lambda *_args, **_kwargs: completed(-11, 'before setup\n', 'native fault'))
    with pytest.raises(AssertionError, match='before.*ei_unref'):
        verifier._check_unref_sentinel('/controlled/eis')


def test_isolated_expected_teardown_fault_retains_its_native_trace(verifier, monkeypatch, capsys):
    trace = 'Fatal Python error: Segmentation fault\n  controlled native frame'
    monkeypatch.setattr(subprocess, 'run', lambda *_args, **_kwargs: completed(-11, READY, trace))
    result = verifier._check_unref_sentinel('/controlled/eis')
    assert 'still segfaults' in result and 'rc=-11' in result
    assert trace in capsys.readouterr().out


@pytest.mark.parametrize('output', ['', READY, READY+DONE])
def test_success_needs_finished_cleanup_and_measured_descriptor_evidence(verifier, monkeypatch, output):
    monkeypatch.setattr(subprocess, 'run', lambda *_args, **_kwargs: completed(0, output))
    with pytest.raises(AssertionError):
        verifier._check_unref_sentinel('/controlled/eis')


def test_completed_cleanup_reports_exact_descriptor_counts(verifier, monkeypatch):
    output = READY+DONE+'EI_UNREF_RESULT='+json.dumps({'fd_before': 4, 'fd_after': 4})+'\n'
    monkeypatch.setattr(subprocess, 'run', lambda *_args, **_kwargs: completed(0, output))
    result = verifier._check_unref_sentinel('/controlled/eis')
    assert 'no longer crashes' in result and '4 -> 4' in result


@pytest.mark.parametrize('before,after', [(4, 5), (4, 4.0), (1, True), (4, None)])
def test_successful_unref_with_invalid_descriptor_evidence_remains_a_failure(verifier, monkeypatch, before, after):
    output = READY+DONE+'EI_UNREF_RESULT='+json.dumps({'fd_before': before, 'fd_after': after})+'\n'
    monkeypatch.setattr(subprocess, 'run', lambda *_args, **_kwargs: completed(0, output))
    with pytest.raises(AssertionError, match='descriptor'):
        verifier._check_unref_sentinel('/controlled/eis')


def test_child_has_a_finite_timeout_and_native_fault_handler(verifier, monkeypatch):
    def run(argv, **kwargs):
        assert 0 < kwargs.get('timeout', 0) <= 30
        assert argv[1:3] == ['-X', 'faulthandler'] and kwargs['check'] is False
        assert kwargs['capture_output'] is True
        compile(argv[-1], '<controlled-native-probe>', 'exec')
        raise subprocess.TimeoutExpired(argv, kwargs['timeout'])

    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(subprocess.TimeoutExpired):
        verifier._check_unref_sentinel('/controlled/eis')


def test_native_refusal_checks_match_the_current_no_silent_fallback_contract(verifier, monkeypatch):
    from je_auto_control.linux_wayland import _select_input, keyboard, libei
    error = libei.LibeiUnavailable('controlled refusal', state='failed')

    def refuse(*_args):
        raise error

    monkeypatch.setattr(_select_input, 'active_backend', refuse)
    monkeypatch.setattr(keyboard, 'press_key', refuse)
    assert 'failed' in verifier._check_native_refusal()
    assert 'failed' in verifier._check_keyboard_refuses_native()


def test_explicit_cli_verification_restores_its_previous_override(verifier, monkeypatch):
    from je_auto_control.linux_wayland import keyboard
    key = 'JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND'
    monkeypatch.setenv(key, 'libei')

    def cli(_code):
        assert verifier.os.environ[key] == 'cli'
        raise RuntimeError('install ydotool')

    monkeypatch.setattr(keyboard, 'press_key', cli)
    assert 'ydotool' in verifier._check_explicit_cli_hint()
    assert verifier.os.environ[key] == 'libei'


def test_dev_native_workflow_runs_both_probes_and_retains_failure_logs():
    path = ROOT/'.github/workflows/ei-lifecycle.yml'
    assert path.exists(), 'dev has no workflow that can collect real EI lifecycle evidence'
    workflow = yaml.load(path.read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
    assert 'dev' in workflow['on']['push']['branches']
    assert workflow['permissions'] == {'contents': 'read'}
    job = workflow['jobs']['ei-lifecycle']
    assert int(job['timeout-minutes']) <= 30
    steps = job['steps']
    build = next(step for step in steps if step.get('id') == 'build')
    assert build['with']['file'] == 'docker/Dockerfile.eis'
    probe = next(step for step in steps if 'libei_verify.py' in step.get('run', ''))
    peer = next(step for step in steps if 'eis_verify.py' in step.get('run', ''))
    assert all(step['shell'] == 'bash' and 'tee native-ei/' in step['run'] for step in (probe, peer))
    assert all('always()' in step['if'] and "steps.build.outcome == 'success'" in step['if'] for step in (probe, peer))
    assert not any(step.get('continue-on-error') == 'true' for step in (probe, peer))
    upload = next(step for step in steps if step.get('uses', '').startswith('actions/upload-artifact@'))
    assert upload['if'] == 'always()' and upload['with']['path'] == 'native-ei/'
    cleanup = next(step for step in steps if step.get('name') == 'Remove owned verification containers')
    assert cleanup['if'] == 'always()' and 'docker rm -f' in cleanup['run']
    assert not any('--privileged' in step.get('run', '') or '--device' in step.get('run', '') for step in steps)
    dockerfile = (ROOT/'docker/Dockerfile.eis').read_text(encoding='utf-8')
    assert 'COPY docker/libei_verify.py /opt/verify/libei_verify.py' in dockerfile
