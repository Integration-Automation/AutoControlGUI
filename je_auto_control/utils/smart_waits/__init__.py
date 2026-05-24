"""Smart waits — frame-diff replacements for ``time.sleep``.

Public surface::

    from je_auto_control import (
        wait_until_screen_stable, wait_until_pixel_changes,
        wait_until_region_idle, WaitOutcome,
    )
"""
from je_auto_control.utils.smart_waits.waits import (
    Frame, ScreenSampler, WaitOutcome,
    wait_until_pixel_changes, wait_until_region_idle,
    wait_until_screen_stable,
)


__all__ = [
    "Frame", "ScreenSampler", "WaitOutcome",
    "wait_until_pixel_changes", "wait_until_region_idle",
    "wait_until_screen_stable",
]
