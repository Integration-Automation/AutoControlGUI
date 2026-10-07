"""Qt-free theme tokens and validated native Qt styling for the workspace."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING

from je_auto_control.gui.tab_registry import TabRegistryError, _require_gui_thread

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


@dataclass(frozen=True)
class ThemePalette:
    """Seven semantic colors shared by light/dark focus, content and error states."""

    background: str
    surface: str
    text: str
    muted: str
    accent: str
    border: str
    error: str


_DARK = ThemePalette('#10151f', '#192231', '#e9eef6', '#9baac0', '#5db9e8', '#344256', '#ff8f94')
_LIGHT = ThemePalette('#eef2f6', '#ffffff', '#18263a', '#5d6c80', '#176b9a', '#bac8d7', '#ac263c')


@dataclass(frozen=True)
class ThemeTokens:
    """Immutable spacing/font/focus tokens; no raster or optional theme dependency."""

    palette: ThemePalette = _DARK
    spacing: int = 10
    font_point_size: int = 12
    radius: int = 6

    @classmethod
    def dark(cls, font_point_size: int = 12) -> ThemeTokens:
        """Create the default dark workspace palette."""
        return cls(_DARK, font_point_size=font_point_size)

    @classmethod
    def light(cls, font_point_size: int = 12) -> ThemeTokens:
        """Create the light workspace palette with the same layout metrics."""
        return cls(_LIGHT, font_point_size=font_point_size)


def apply_theme(window: QWidget, theme: ThemeTokens) -> None:
    """Apply one validated palette/font without erasing focus or responsive layout rules."""
    _require_gui_thread()
    _validate(theme)
    # pylint: disable-next=import-outside-toplevel  # reason: Qt-free token imports; styling explicitly requires the GUI
    from PySide6.QtGui import QFontDatabase
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    font.setPointSize(theme.font_point_size)
    window.setFont(font)
    window.setStyleSheet(_stylesheet(theme))


def _validate(theme: ThemeTokens) -> None:
    if not isinstance(theme, ThemeTokens) or not isinstance(theme.palette, ThemePalette):
        raise TabRegistryError('workspace theme requires typed ThemeTokens/ThemePalette')
    if any(not isinstance(value, str) or re.fullmatch(r'#[0-9a-fA-F]{6}', value) is None
           for value in vars(theme.palette).values()):
        raise TabRegistryError('theme colors must be six-digit hexadecimal values')
    for value, low, high in [(theme.spacing, 0, 32), (theme.font_point_size, 6, 24), (theme.radius, 0, 24)]:
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise TabRegistryError('theme spacing/font/radius is outside the supported range')


def _stylesheet(theme: ThemeTokens) -> str:
    p = theme.palette
    padding = theme.spacing // 2
    return f'''
QWidget {{ background: {p.background}; color: {p.text}; font-size: {theme.font_point_size}pt; }}
QMenu, QMenuBar, QTabWidget::pane, QFrame[role="surface"] {{ background: {p.surface}; }}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {p.surface}; border: 2px solid {p.border}; border-radius: {theme.radius}px; padding: {padding}px;
    selection-background-color: {p.accent}; selection-color: {p.background};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border-color: {p.accent}; }}
QTreeWidget, QListWidget, QTableWidget {{ background: {p.surface}; border: 1px solid {p.border}; }}
QTreeWidget::item {{ padding: {padding}px; }}
QTreeWidget::item:selected, QMenu::item:selected {{ background: {p.accent}; color: {p.background}; }}
QPushButton, QToolButton {{ background: {p.surface}; border: 1px solid {p.border};
    border-radius: {theme.radius}px; padding: {padding}px {theme.spacing}px; }}
QPushButton:focus, QToolButton:focus, QPushButton:hover, QToolButton:hover {{ border-color: {p.accent}; }}
QTabBar::tab {{ background: {p.surface}; padding: 8px 12px; border-bottom: 2px solid {p.border}; }}
QTabBar::tab:selected {{ border-bottom-color: {p.accent}; }}
QLabel[role="muted"] {{ color: {p.muted}; }}
QLabel[role="heading"] {{ font-weight: bold; font-size: {theme.font_point_size + 2}pt; }}
QLabel[role="error"] {{ color: {p.error}; }}
QSplitter::handle {{ background: {p.border}; width: 1px; }}
QScrollArea {{ border: none; }}
QProgressBar {{ border: 1px solid {p.border}; border-radius: {theme.radius}px; text-align: center; }}
QProgressBar::chunk {{ background: {p.accent}; }}
'''


__all__ = ['ThemePalette', 'ThemeTokens', 'apply_theme']
