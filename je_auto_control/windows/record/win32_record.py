"""Windows recorder: the low-level input hook shaped into the recorder surface.

Everything after the capture — the down-events-only queue the executor has
always been handed, the ``delta_ms`` timeline a replay needs, and the
mouse-only / keyboard-only filters — is platform-neutral and lives in
:mod:`je_auto_control.utils.input_macro.recorder_base`, so this backend and
the macOS one cannot drift in the shape they produce.
"""
import sys

from je_auto_control.utils.exception.exception_tags import windows_import_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.input_macro.recorder_base import InputRecorder

if sys.platform not in ["win32", "cygwin", "msys"]:
    raise AutoControlException(windows_import_error_message)

from je_auto_control.windows.record.win32_input_hook import Win32InputHook


class Win32Recorder(InputRecorder):
    """
    Win32Recorder
    Windows 錄製器
    - 可同時錄製滑鼠與鍵盤事件
    - 可選擇只錄製滑鼠或鍵盤

    Capture runs through :class:`Win32InputHook`, which records releases,
    wheel movement and timing as well as presses. ``stop_record`` still
    returns the historical down-events-only queue so existing callers are
    unaffected; use ``stop_record_timeline`` for everything needed to
    reproduce the session.
    """

    def new_hook(self) -> Win32InputHook:
        """Return a fresh, uninstalled hook."""
        return Win32InputHook()


# 全域錄製器實例 Global recorder instance
win32_recorder = Win32Recorder()
