"""macOS backend imports must not load native frameworks for pure CLI failures."""
from headless._exit_probe import run_probe


_IMPORT = r'''
import importlib.abc
import sys

class NativeImportBlocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('Quartz', 'AppKit'):
            raise AssertionError('native framework loaded before a native operation: ' + fullname)

sys.meta_path.insert(0, NativeImportBlocker())
import je_auto_control
sys.platform = 'darwin'
from je_auto_control.wrapper import _platform_osx as backend
from je_auto_control.osx.pid import pid_control
assert callable(backend.keyboard.press_key)
assert callable(backend.mouse.press_mouse)
assert callable(backend.screen.size)
assert callable(pid_control.send_key_to_pid)
assert backend.recorder.stop_record_timeline() == []
assert 'je_auto_control.osx.listener.osx_listener' not in sys.modules
assert 'Quartz' not in sys.modules and 'AppKit' not in sys.modules
try:
    backend.keyboard.special_key('unknown-key', True)
except ValueError:
    pass
else:
    raise AssertionError('unknown key was accepted')
'''


def test_mac_backend_and_idle_recorder_do_not_import_native_frameworks():
    result = run_probe(_IMPORT, 'import')
    assert result.returncode == 0, result.stdout + result.stderr


def test_deferred_framework_operations_reach_the_injected_native_module():
    calls = r'''
import types
posted = []
quartz = types.ModuleType('Quartz')
quartz.CGEventSourceKeyState = lambda source, code: (source, code) == (0, 5)
quartz.CGMainDisplayID = lambda: 17
quartz.CGDisplayPixelsWide = lambda display: 123 if display == 17 else 0
quartz.CGDisplayPixelsHigh = lambda display: 456 if display == 17 else 0
quartz.CGEventCreateKeyboardEvent = lambda source, code, down: (source, code, down)
quartz.CGEventPostToPid = lambda pid, event: posted.append((pid, event))
sys.modules['Quartz'] = quartz
assert backend.keyboard_check.check_key_is_press(5) is True
assert backend.screen.size() == (123, 456)
pid_control.send_key_to_pid(19, 7)
assert posted == [(19, (None, 7, True)), (19, (None, 7, False))]
'''
    result = run_probe(_IMPORT + calls, 'native-seam')
    assert result.returncode == 0, result.stdout + result.stderr
