"""Smart waits — frame-diff replacements for ``time.sleep``.

Public surface::

    from je_auto_control import (
        wait_until_screen_stable, wait_until_pixel_changes,
        wait_until_region_idle, WaitOutcome,
    )
"""
from je_auto_control.utils.smart_waits.waits import (
    ClipboardReader, FileStatReader, Frame, PortConnector, ProcessLister,
    ScreenSampler, WaitOutcome, WindowFinder, wait_until_clipboard_changes,
    wait_until_color, wait_until_file, wait_until_gone, wait_until_image_gone,
    wait_until_pixel_changes, wait_until_port, wait_until_process,
    wait_until_region_idle, wait_until_screen_stable, wait_until_text_gone,
    wait_until_window_closed,
)


__all__ = [
    "ClipboardReader", "FileStatReader", "Frame", "PortConnector",
    "ProcessLister", "ScreenSampler", "WaitOutcome", "WindowFinder",
    "wait_until_clipboard_changes", "wait_until_color", "wait_until_file",
    "wait_until_gone", "wait_until_image_gone", "wait_until_pixel_changes",
    "wait_until_port", "wait_until_process", "wait_until_region_idle",
    "wait_until_screen_stable", "wait_until_text_gone",
    "wait_until_window_closed",
]
