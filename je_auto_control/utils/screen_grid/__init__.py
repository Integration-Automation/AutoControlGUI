"""Coarse labelled cell grid for VLM grounding (point <-> cell mapping)."""
from je_auto_control.utils.screen_grid.screen_grid import (
    GridCell, cell_for_point, grid_cells, point_for_cell,
)

__all__ = ["GridCell", "cell_for_point", "grid_cells", "point_for_cell"]
