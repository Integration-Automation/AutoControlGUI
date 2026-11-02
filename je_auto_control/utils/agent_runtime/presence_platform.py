"""Pick the physical presence API for this helper's platform; a platform without a trusted source refuses."""
from __future__ import annotations

import math
import os
import sys
from typing import Any, Mapping

from je_auto_control.utils.agent_runtime.errors import AgentTaskError


def presence_backend(platform: str = sys.platform, environ: Mapping[str, str] | None = None) -> str:
    """Name the trusted source for a platform: ``win32``, ``quartz`` or ``x11``, else ``unsupported``."""
    environ = os.environ if environ is None else environ
    if platform == 'win32':
        return 'win32'
    if platform == 'darwin':
        return 'quartz'
    if platform.startswith('linux'):
        # Wayland clients see no global input and cannot tell a person from libei/uinput injection.
        wayland = environ.get('XDG_SESSION_TYPE', '').lower() == 'wayland' or bool(environ.get('WAYLAND_DISPLAY'))
        if environ.get('DISPLAY') and not wayland:
            return 'x11'
    return 'unsupported'


def require_poll_timeout(timeout: object) -> None:
    """Accept only the finite, at most fifty-millisecond waits every presence API polls with."""
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not 0 <= timeout <= 0.05 or not math.isfinite(timeout)):
        raise AgentTaskError('physical presence poll deadline must be finite and at most fifty milliseconds')


def default_presence_api(platform: str = sys.platform, environ: Mapping[str, str] | None = None) -> Any:
    """Construct the platform's inert presence API; nothing native opens until ``open``."""
    backend = presence_backend(platform, environ)
    # pylint: disable=import-outside-toplevel  # reason: each backend loads only on its own platform
    if backend == 'win32':
        from je_auto_control.utils.agent_runtime.presence_win32 import Win32PresenceAPI
        return Win32PresenceAPI()
    if backend == 'quartz':
        from je_auto_control.utils.agent_runtime.presence_quartz import QuartzPresenceAPI
        return QuartzPresenceAPI()
    if backend == 'x11':
        from je_auto_control.utils.agent_runtime.presence_x11 import X11PresenceAPI
        return X11PresenceAPI()
    raise AgentTaskError(f'no trusted physical presence source for {platform}')


def default_presence_pipe(namespace: str | None = None) -> Any:
    """The pipe factory a presence server or broker uses on this platform; nothing native opens yet."""
    # pylint: disable=import-outside-toplevel  # reason: each transport loads only on its own platform
    if sys.platform.startswith('linux'):
        from je_auto_control.utils.agent_runtime.presence_pipe_linux import LinuxPresencePipe
        return LinuxPresencePipe(namespace=namespace)
    from je_auto_control.utils.agent_runtime.presence_pipe_windows import WindowsPresencePipe
    return WindowsPresencePipe(namespace=namespace)


def default_presence_security() -> Any:
    """The peer-evidence provider the presence handshake uses on this platform."""
    # pylint: disable=import-outside-toplevel  # reason: each transport loads only on its own platform
    if sys.platform.startswith('linux'):
        from je_auto_control.utils.agent_runtime.presence_pipe_linux import LinuxPresenceSecurity
        return LinuxPresenceSecurity()
    from je_auto_control.utils.agent_runtime.presence_security_windows import WindowsPresenceSecurity
    return WindowsPresenceSecurity()
