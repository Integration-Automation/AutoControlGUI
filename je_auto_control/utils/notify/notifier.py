"""Send a cross-platform desktop notification (title + message).

Useful for long-running automation: ping the operator when a flow
finishes or an assertion fails. The notifier never raises — a missing
backend just yields ``NotifyResult(shown=False, ...)``.

Security: no ``shell=True`` and no command strings built from input.
Linux passes the strings as separate ``notify-send`` argv. macOS and
Windows run a *static* script (AppleScript / PowerShell) that reads the
title and message from environment variables, so user text never lands
in the command line — no injection surface.
"""
import os
import platform
import subprocess  # nosec B404 — argv lists only; see module docstring
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

from je_auto_control.utils.logging.logging_instance import autocontrol_logger

_MAC_SCRIPT = (
    'display notification (system attribute "AC_NOTIFY_MSG") '
    'with title (system attribute "AC_NOTIFY_TITLE")'
)

_WINDOWS_SCRIPT = (
    "$t=$env:AC_NOTIFY_TITLE; $m=$env:AC_NOTIFY_MSG; "
    "[void][Windows.UI.Notifications.ToastNotificationManager,"
    "Windows.UI.Notifications,ContentType=WindowsRuntime]; "
    "$x=[Windows.UI.Notifications.ToastNotificationManager]::"
    "GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]"
    "::ToastText02); $n=$x.GetElementsByTagName('text'); "
    "[void]$n.Item(0).AppendChild($x.CreateTextNode($t)); "
    "[void]$n.Item(1).AppendChild($x.CreateTextNode($m)); "
    "$toast=[Windows.UI.Notifications.ToastNotification]::new($x); "
    "[Windows.UI.Notifications.ToastNotificationManager]::"
    "CreateToastNotifier('AutoControl').Show($toast)"
)


@dataclass(frozen=True)
class NotifyResult:
    """Outcome of a notification attempt."""

    shown: bool
    backend: str
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _notify_spec(system: str, title: str, message: str
                 ) -> Tuple[Optional[List[str]], Dict[str, str]]:
    """Return ``(argv, env_extra)`` for a notification on ``system``.

    ``argv`` is ``None`` when the platform is unsupported. Pure and
    side-effect-free so it can be unit-tested off the target OS.
    """
    if system == "Darwin":
        return (["osascript", "-e", _MAC_SCRIPT],
                {"AC_NOTIFY_TITLE": title, "AC_NOTIFY_MSG": message})
    if system == "Linux":
        return (["notify-send", "--", title, message], {})
    if system == "Windows":
        return (["powershell", "-NoProfile", "-NonInteractive",
                 "-Command", _WINDOWS_SCRIPT],
                {"AC_NOTIFY_TITLE": title, "AC_NOTIFY_MSG": message})
    return (None, {})


def notify(title: str, message: str,
           system: Optional[str] = None) -> NotifyResult:
    """Show a desktop notification; return a :class:`NotifyResult`.

    Best-effort and non-raising: an unsupported platform or a missing
    notifier tool yields ``shown=False`` with a reason.
    """
    system = system or platform.system()
    argv, env_extra = _notify_spec(system, str(title), str(message))
    if argv is None:
        return NotifyResult(False, system, "no notifier for platform")
    try:
        subprocess.run(  # nosec B603 B607 — argv list, static script, env-passed strings  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit.dangerous-subprocess-use-audit
            argv, env={**os.environ, **env_extra}, timeout=10, check=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return NotifyResult(True, system, "sent")
    except (FileNotFoundError, OSError, subprocess.SubprocessError) as error:
        autocontrol_logger.warning("notify failed: %r", error)
        return NotifyResult(False, system, repr(error))
