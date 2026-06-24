"""Read rich UIA element properties (enabled / offscreen / help / status / keys)."""
from je_auto_control.utils.ax_props.ax_props import (
    get_element_properties, is_element_enabled,
)

__all__ = ["get_element_properties", "is_element_enabled"]
