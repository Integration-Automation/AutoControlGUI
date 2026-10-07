"""Native Android install/files/Unicode clipboard through explicit owned clients."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from je_auto_control.wrapper._mobile_models import DeviceSessionError

if TYPE_CHECKING:
    from je_auto_control.wrapper.device_context import DeviceSession


class AndroidExtension:
    """Use bounded ADB transfers and the owned SDK clipboard; never start a recorder."""

    name, version = 'android-native', '1'

    def __init__(self, session: DeviceSession) -> None:
        self._session = session
        self.context = session.context
        self.capabilities = {key: session.capabilities[key] for key in ('install', 'files', 'clipboard')}

    def install(self, file_path: str) -> None:
        """Install the selected APK and require ADB's explicit success confirmation."""
        result = self._session.adapter('adb').run(['install', '-r', file_path])
        if b'Success' not in result.stdout.splitlines():
            raise DeviceSessionError('ADB did not confirm application installation')

    def files(self, action: str, local_path: str, remote_path: str) -> None:
        """Transfer exactly the selected file using explicit device serial/timeout."""
        source, destination = (local_path, remote_path) if action == 'push' else (remote_path, local_path)
        self._session.adapter('adb').run([action, source, destination])

    def clipboard(self, text: Optional[str] = None) -> Optional[str]:
        """Read/write exact Unicode through the SDK's native clipboard endpoint."""
        handle = self._session.adapter('uiautomator2').handle
        if text is not None:
            handle.set_clipboard(text)
            return None
        value = handle.clipboard
        if not isinstance(value, str):
            raise DeviceSessionError('Android clipboard returned non-text data')
        return value

    def recording(self, file_path: str, duration_s: float) -> None:
        """Require a configured owned recording adapter rather than fake success."""
        raise DeviceSessionError('needs_dependency: configure an owned MobileExtension recording adapter')

    def close(self) -> None:
        """Clients remain owned and reclaimed by the enclosing DeviceSession."""
