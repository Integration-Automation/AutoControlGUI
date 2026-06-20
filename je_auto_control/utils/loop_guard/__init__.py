"""Mechanical stuck-loop detection for agent loops."""
from je_auto_control.utils.loop_guard.loop_guard import (
    LoopGuard, LoopVerdict, default_loop_guard, digest_result,
)

__all__ = [
    "LoopGuard", "LoopVerdict", "default_loop_guard", "digest_result",
]
