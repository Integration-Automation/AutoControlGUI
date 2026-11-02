"""Windows USB enumeration preserves Unicode streams without reader-thread failures or visible consoles."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

import je_auto_control


_WORKER = r'''
import json, subprocess, sys, threading
from pathlib import Path
import je_auto_control
from je_auto_control.utils.usb import usb_devices

assert Path(je_auto_control.__file__).resolve().is_relative_to(Path(sys.argv[3]))
expected = json.loads(sys.argv[1])
exit_code = int(sys.argv[2])
query = ("Get-PnpDevice -PresentOnly -Class USB"
         " | Select-Object FriendlyName, InstanceId, Manufacturer, Status"
         " | ConvertTo-Json -Compress")
real_run = subprocess.run
errors, observed_flags = [], []
threading.excepthook = lambda args: errors.append(type(args.exc_value).__name__)

def synthetic_query(argv, **options):
    assert argv[:4] == ['powershell', '-NoProfile', '-NonInteractive', '-Command']
    assert argv[-1].endswith(query)
    payload = json.dumps(expected, ensure_ascii=False).replace("'", "''")
    diagnostic = 'diagnostic ' + chr(0x6e2c) + chr(0x8a66) + chr(0x1f9ea)
    body = "[Console]::Error.Write('" + diagnostic + "'); "
    if not exit_code:
        body += "[Console]::Write('" + payload + "'); "
    body += 'exit ' + str(exit_code)
    command = [*argv[:-1], argv[-1][:-len(query)] + body]
    flags = options.get('creationflags', 0)
    observed_flags.append(flags)
    # The RED control must also stay hidden even before the library supplies the required flag.
    options['creationflags'] = flags | subprocess.CREATE_NO_WINDOW
    return real_run(command, **options)

usb_devices.subprocess.run = synthetic_query
result = usb_devices._enumerate_windows()
assert errors == [], ('background stream decoding failed', errors)
if exit_code:
    assert result.devices == []
    assert 'diagnostic ' + chr(0x6e2c) + chr(0x8a66) + chr(0x1f9ea) in result.error, result.error
else:
    assert result.error is None, result.error
    assert len(result.devices) == 1
    assert result.devices[0].product == expected['FriendlyName'], result.to_dict()
    assert result.devices[0].manufacturer == expected['Manufacturer'], result.to_dict()
assert observed_flags and all(value & subprocess.CREATE_NO_WINDOW for value in observed_flags)
print(json.dumps({'utf8_mode': sys.flags.utf8_mode, 'exit_code': exit_code,
                  'unicode_preserved': True, 'reader_errors': errors, 'console_hidden': True}))
'''


@pytest.mark.skipif(sys.platform != 'win32' or shutil.which('powershell') is None,
                    reason='requires Windows PowerShell byte-stream producer')
@pytest.mark.parametrize('utf8_mode', ['0', '1'])
@pytest.mark.parametrize('exit_code', [0, 7])
def test_usb_unicode_streams_are_independent_of_python_utf8_mode(utf8_mode, exit_code, tmp_path):
    expected = {'FriendlyName': '測試 USB 🧪', 'Manufacturer': '製造商 🧪',
                'InstanceId': 'USB\\VID_1234&PID_5678\\TEST', 'Status': 'OK'}
    project = Path(__file__).resolve().parents[3]
    package_parent = Path(je_auto_control.__file__).resolve().parent.parent
    environment = dict(os.environ, PYTHONUTF8=utf8_mode, PYTHONIOENCODING='utf-8',
                       PYTHONPATH=os.pathsep.join([str(package_parent), str(project)]),
                       JE_AUTOCONTROL_LOG_FILE=str(tmp_path / 'owned-usb.log'))
    completed = subprocess.run(
        [sys.executable, '-c', _WORKER, json.dumps(expected), str(exit_code), str(package_parent)],
        cwd=tmp_path, env=environment, capture_output=True, encoding='utf-8',
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=15, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(completed.stdout) == {'utf8_mode': int(utf8_mode), 'exit_code': exit_code,
                                           'unicode_preserved': True, 'reader_errors': [], 'console_hidden': True}
