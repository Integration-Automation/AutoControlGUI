"""Resource-free native structure views shared by presence observation and pipe security."""
import ctypes
from typing import Any


class NativeLayout(ctypes.Structure):
    """Expose size and a nonowning pointer for explicit Win32 structure arguments."""

    @classmethod
    def size(cls) -> int:
        """Return the actual ABI size of this native layout."""
        return ctypes.sizeof(cls)

    def pointer(self) -> Any:
        """Borrow this structure's memory only for the duration of a native call."""
        return ctypes.byref(self)
