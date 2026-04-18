"""Public API for drag-to-select region picking."""
from typing import Optional, Tuple

from PySide6.QtWidgets import QWidget

from je_auto_control.gui.selector.region_overlay import pick_region_blocking


def open_region_selector(parent: Optional[QWidget] = None
                         ) -> Optional[Tuple[int, int, int, int]]:
    """
    Display a full-screen overlay and return the chosen (x, y, w, h) region.

    :param parent: optional parent widget (currently unused; the overlay is top-level)
    :return: (x, y, width, height) in virtual-desktop coordinates, or None if cancelled
    """
    return pick_region_blocking(parent)
