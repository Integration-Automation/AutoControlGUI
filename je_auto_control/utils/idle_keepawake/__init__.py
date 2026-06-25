"""Detect user-idle time and keep the machine awake during unattended runs."""
from je_auto_control.utils.idle_keepawake.idle_keepawake import (
    allow_sleep, idle_seconds, is_idle, keep_awake, keep_awake_on,
    plan_keep_awake,
)

__all__ = [
    "idle_seconds", "is_idle", "plan_keep_awake",
    "keep_awake", "keep_awake_on", "allow_sleep",
]
