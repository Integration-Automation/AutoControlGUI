"""GUI package — kept import-light so individual tabs can be loaded without
pulling in the full main window (which transitively requires the optional
``webrtc`` extra). The launcher imports its dependencies lazily inside
:func:`start_autocontrol_gui` so::

    from je_auto_control.gui.profiler_tab import ProfilerTab

works in environments that have not installed PyAV / aiortc.
"""


def start_autocontrol_gui() -> None:
    """Open the AutoControl GUI; pulls in PySide6 + WebRTC stack lazily."""
    import sys

    from PySide6.QtWidgets import QApplication

    from je_auto_control.gui.main_window import AutoControlGUIUI

    app = QApplication(sys.argv)
    window = AutoControlGUIUI()
    window.show()
    sys.exit(app.exec())
