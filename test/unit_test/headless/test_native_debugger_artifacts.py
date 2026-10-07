"""Native diagnostics must never hide target failure or claim success without target exit evidence."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

_SPEC = importlib.util.spec_from_file_location(
    'ac_native_debugger', Path(__file__).resolve().parents[2] / 'verify' / 'native_debugger.py')
assert _SPEC is not None and _SPEC.loader is not None
native_debugger = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(native_debugger)


@pytest.mark.parametrize('target_code', [0, 17])
def test_target_exit_is_preserved_even_if_debugger_exits_zero(tmp_path, monkeypatch, target_code):
    def fake(command, output, target_platform):
        report = str(output / 'target-exit.txt')
        return [sys.executable, '-c',
                f"open({report!r}, 'w').write('{target_code}'); print('native-frame-marker')"]

    monkeypatch.setattr(native_debugger, '_debugger_command', fake)
    assert native_debugger.run_diagnostic(
        ['python', '-m', 'coverage'], tmp_path, target_platform='linux') == target_code
    metadata = json.loads((tmp_path / 'run.json').read_text(encoding='utf-8'))
    assert metadata['target_exit'] == target_code and metadata['debugger_exit'] == 0
    assert 'native-frame-marker' in (tmp_path / 'native-debugger.log').read_text(encoding='utf-8')


def test_missing_target_evidence_is_not_a_success(tmp_path, monkeypatch):
    monkeypatch.setattr(native_debugger, '_debugger_command',
                        lambda *args: [sys.executable, '-c', "print('debugger could not launch target')"])
    assert native_debugger.run_diagnostic(['python'], tmp_path, target_platform='linux') == 1
    assert json.loads((tmp_path / 'run.json').read_text(encoding='utf-8'))['state'] == 'debugger_error'


def test_timeout_kills_owned_debugger_and_retains_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(native_debugger, '_debugger_command',
                        lambda *args: [sys.executable, '-c', 'import time; time.sleep(30)'])
    assert native_debugger.run_diagnostic(['python'], tmp_path, target_platform='darwin', timeout_s=0.1) == 124
    assert json.loads((tmp_path / 'run.json').read_text(encoding='utf-8'))['state'] == 'timeout'


@pytest.mark.parametrize('platform_name,timeout', [('win32', 1), ('linux', float('inf')), ('darwin', -1)])
def test_invalid_profile_fails_before_launch(tmp_path, platform_name, timeout):
    with pytest.raises(ValueError):
        native_debugger.run_diagnostic(['python'], tmp_path, target_platform=platform_name, timeout_s=timeout)


@pytest.mark.parametrize('exited,reason,native_signal,expected', [
    (True, 7, 6, '17'), (False, 5, 6, '134'), (False, 7, 6, None), (False, 5, 2, None),
])
def test_lldb_nonfatal_stops_cannot_be_reported_as_a_native_crash(tmp_path, exited, reason, native_signal, expected):
    thread = SimpleNamespace(GetStopReason=lambda: reason, GetStopReasonDataAtIndex=lambda _index: native_signal)
    process = SimpleNamespace(GetState=lambda: 10 if exited else 0, GetExitStatus=lambda: 17,
                              GetSelectedThread=lambda: thread, Kill=lambda: None)
    target = SimpleNamespace(GetProcess=lambda: process)
    debugger = SimpleNamespace(GetSelectedTarget=lambda: target, HandleCommand=lambda _command: None)
    namespace = {'lldb': SimpleNamespace(debugger=debugger, eStateExited=10,
                                        eStopReasonSignal=5, eStopReasonException=6)}
    report = tmp_path / 'target-exit.txt'
    commands = native_debugger._lldb_script(report)
    assert 'settings set target.process.stop-on-exec false' in commands
    assert 'process handle SIGINT -n false -p true -s false' in commands
    assert 'handle SIGINT nostop noprint pass' in native_debugger._gdb_script(report)
    for line in commands.splitlines():
        if line.startswith('script '):
            exec(line[7:], namespace)  # pylint: disable=exec-used  # Executes only this tool's generated fixed script.
    assert report.read_text(encoding='ascii') == expected if expected is not None else not report.exists()
