"""Wait until an application stops being busy before driving the next step."""
from je_auto_control.utils.app_idle.app_idle import (
    idle_point, wait_until_app_idle,
)

__all__ = ["wait_until_app_idle", "idle_point"]
