"""Background popup/interrupt watchdog for unattended automation."""
from je_auto_control.utils.watchdog.popup_watchdog import (
    PopupWatchdog, WatchdogRule, default_popup_watchdog,
)

__all__ = ["PopupWatchdog", "WatchdogRule", "default_popup_watchdog"]
