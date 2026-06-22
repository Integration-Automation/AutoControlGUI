"""Window tiling/layout geometry planner (halves, quadrants, grids, cascade)."""
from je_auto_control.utils.window_layout.window_layout import (
    WindowRect, available_slots, cascade_rects, grid_rects, tile_rect,
)

__all__ = ["WindowRect", "available_slots", "cascade_rects", "grid_rects",
           "tile_rect"]
