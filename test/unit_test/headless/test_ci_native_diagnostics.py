"""CI diagnostics retain evidence without turning ordinary/native failures into success."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

SCRIPT = Path(__file__).resolve().parents[3] / 'scripts/ci_native_diagnostics.py'
WORKFLOWS = SCRIPT.parent.parent / '.github/workflows'


def run_child(directory, code, *flags):
    return subprocess.run([sys.executable, str(SCRIPT), '--artifact-dir', str(directory), *flags,
                           '--', sys.executable, '-c', code], capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=30, check=False)


@pytest.mark.parametrize('exit_code', [0, 7])
@pytest.mark.parametrize('native', [False, True])
def test_child_result_output_and_runtime_versions_survive_the_wrapper(tmp_path, monkeypatch, exit_code, native):
    if native and (sys.platform != 'linux' or shutil.which('gdb') is None):
        pytest.skip('requires Linux GDB')
    monkeypatch.setenv('AC_CONTROLLED_PRIVATE_TEST_VALUE', 'private-native-runner-sentinel')
    directory = tmp_path / 'evidence'
    result = run_child(directory, f"print('controlled child evidence');raise SystemExit({exit_code})",
                       *(['--native'] if native else []))
    assert result.returncode == exit_code
    assert 'controlled child evidence' in result.stdout
    log = (directory / 'process.log').read_text(encoding='utf-8')
    raw = (directory / 'runtime.json').read_text(encoding='utf-8')
    record = json.loads(raw)
    assert 'controlled child evidence' in log
    assert record['returncode'] == exit_code and record['elapsed_seconds'] >= 0
    assert record['packages']['pytest'] and record['python']
    assert 'private-native-runner-sentinel' not in log + raw
    assert 'AC_CONTROLLED_PRIVATE_TEST_VALUE' not in log + raw


@pytest.mark.skipif(sys.platform != 'linux' or shutil.which('gdb') is None, reason='requires Linux GDB')
def test_real_native_abort_retains_a_backtrace_and_fails(tmp_path):
    directory = tmp_path / 'native-abort'
    result = run_child(directory, "import os;print('before native abort',flush=True);os.abort()", '--native')
    assert result.returncode != 0
    log = (directory / 'process.log').read_text(encoding='utf-8')
    record = json.loads((directory / 'runtime.json').read_text(encoding='utf-8'))
    assert 'before native abort' in log and 'SIGABRT' in log
    assert '#0 ' in log and ('abort' in log or 'raise' in log)
    assert record['returncode'] != 0 and record['debugger']


def test_requested_native_debugging_never_silently_runs_without_the_debugger(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('native_diagnostics_probe', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.shutil, 'which', lambda _name: None)
    with pytest.raises(RuntimeError, match='requires gdb'):
        module.run([sys.executable, '-c', 'raise SystemExit(0)'], tmp_path / 'missing', native=True)


def test_unwritable_evidence_destination_prevents_launching_the_child(tmp_path):
    destination = tmp_path / 'existing-file'
    destination.write_text('preserve this file', encoding='utf-8')
    marker = tmp_path / 'must-not-launch'
    result = run_child(destination, f'from pathlib import Path;Path({str(marker)!r}).touch()')
    assert result.returncode != 0 and not marker.exists()
    assert destination.read_text(encoding='utf-8') == 'preserve this file'


@pytest.mark.parametrize('name', ['dev.yml', 'quality.yml'])
def test_ci_workflows_keep_native_diagnostics_after_failure(name):
    workflow = yaml.safe_load((WORKFLOWS / name).read_text(encoding='utf-8'))
    steps = workflow['jobs']['pytest-headless']['steps']
    upload = next(step for step in steps if step.get('with', {}).get('name', '').startswith('native-'))
    assert upload['if'] == 'always()' and upload['uses'].startswith('actions/upload-artifact@')
    runner = next(step for step in steps if 'scripts/ci_native_diagnostics.py' in step.get('run', ''))
    assert '--native' in runner['run'] and '--artifact-dir' in runner['run']
    assert upload['with']['path'] in runner['run']
    assert ('python -m coverage run -m pytest' if name == 'quality.yml' else 'python -m pytest') in runner['run']
    assert any('gdb' in step.get('run', '') and step.get('if') == "runner.os == 'Linux'" for step in steps)
