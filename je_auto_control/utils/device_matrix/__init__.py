"""Mobile device matrix — parallel script execution across devices.

Public surface::

    from je_auto_control import run_on_devices, DeviceResult, MatrixReport
"""
from je_auto_control.utils.device_matrix.matrix import (
    DeviceResult,
    MatrixReport,
    run_on_devices,
)


__all__ = ["DeviceResult", "MatrixReport", "run_on_devices"]
