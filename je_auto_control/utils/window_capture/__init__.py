"""Per-window capture, window-layout save / restore, snap/tile, and arrange."""
from je_auto_control.utils.window_capture.window_capture import (
    arrange_cascade, arrange_grid, capture_window, get_window_geometry,
    restore_window_layout, save_window_layout, snap_window,
)

__all__ = [
    "arrange_cascade",
    "arrange_grid",
    "capture_window",
    "get_window_geometry",
    "restore_window_layout",
    "save_window_layout",
    "snap_window",
]
