"""macOS recorder: the Quartz event tap shaped into the recorder surface.

Everything after the capture — the down-events-only queue the executor has
always been handed, the ``delta_ms`` timeline a replay needs, and the
mouse-only / keyboard-only filters — is platform-neutral and lives in
:mod:`je_auto_control.utils.input_macro.recorder_base`, so this backend and
the Windows one cannot drift in the shape they produce.
"""
import sys

from je_auto_control.utils.exception.exception_tags import (
    osx_import_error_message,
)
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.input_macro.recorder_base import InputRecorder

# === 平台檢查 Platform Check ===
# 僅允許在 macOS (Darwin) 環境執行，否則拋出例外
if sys.platform not in ["darwin"]:
    raise AutoControlException(osx_import_error_message)

from je_auto_control.osx.listener.osx_listener import OSXInputTap


class OSXRecorder(InputRecorder):
    """
    OSXRecorder
    macOS 事件錄製控制器

    Capture runs through :class:`OSXInputTap`, a listen-only ``CGEventTap`` on
    its own thread, so ``record()`` returns immediately and the user's input
    keeps working while it is being recorded.
    """

    def new_hook(self) -> OSXInputTap:
        """Return a fresh, unstarted event tap."""
        return OSXInputTap()


# === 全域 Recorder 實例 Global Recorder Instance ===
osx_recorder = OSXRecorder()
