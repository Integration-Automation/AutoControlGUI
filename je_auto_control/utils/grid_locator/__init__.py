"""Address a table / grid cell by (row, column) from bounding boxes."""
from je_auto_control.utils.grid_locator.grid_locator import (
    cluster_grid, locate_cell,
)

__all__ = ["cluster_grid", "locate_cell"]
