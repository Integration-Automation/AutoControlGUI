"""Read and control the system master volume and mute state."""
from je_auto_control.utils.system_volume.system_volume import (
    VolumeDriver, change_volume, clamp_percent, get_volume, is_muted, mute,
    percent_to_scalar, scalar_to_percent, set_mute, set_volume, toggle_mute,
    unmute,
)

__all__ = [
    "VolumeDriver", "get_volume", "set_volume", "change_volume",
    "is_muted", "set_mute", "mute", "unmute", "toggle_mute",
    "clamp_percent", "percent_to_scalar", "scalar_to_percent",
]
