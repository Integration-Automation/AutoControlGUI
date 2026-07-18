"""Round-3 GUI audit regression: applying the font must not wipe the theme.

``_apply_font_pt`` used to call ``setStyleSheet("font-size: ...")`` which
*replaces* the widget stylesheet, discarding the qt_material theme that
``apply_stylesheet`` had just installed (finding 5). The font rule must now be
merged on top of the captured theme stylesheet instead.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication, QMainWindow  # noqa: E402

from je_auto_control.gui.main_window import AutoControlGUIUI  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_apply_font_pt_preserves_theme_stylesheet(qapp):
    # A bare QMainWindow stands in for the real window so the whole tab set is
    # not constructed; _apply_font_pt only touches _theme_stylesheet,
    # _detect_auto_font_pt (skipped for pt > 0) and setStyleSheet.
    window = QMainWindow()
    window._theme_stylesheet = "QWidget { color: rgb(1, 2, 3); }"
    try:
        AutoControlGUIUI._apply_font_pt(window, 14)
        sheet = window.styleSheet()
        assert "color: rgb(1, 2, 3)" in sheet  # theme kept
        assert "font-size: 14pt" in sheet      # font applied
    finally:
        window.deleteLater()


def test_apply_font_pt_keeps_theme_across_size_changes(qapp):
    window = QMainWindow()
    window._theme_stylesheet = "QPushButton { background: rgb(9, 9, 9); }"
    try:
        AutoControlGUIUI._apply_font_pt(window, 12)
        AutoControlGUIUI._apply_font_pt(window, 20)  # simulate a text-size change
        sheet = window.styleSheet()
        assert "background: rgb(9, 9, 9)" in sheet  # theme survives the change
        assert "font-size: 20pt" in sheet
        assert "font-size: 12pt" not in sheet  # old rule fully replaced
    finally:
        window.deleteLater()
