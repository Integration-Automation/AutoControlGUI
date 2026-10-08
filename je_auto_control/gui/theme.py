"""Design tokens and the stylesheet built from them.

One :class:`ThemeTokens` value holds every colour, radius and spacing the
window uses; :func:`build_stylesheet` turns it into Qt style sheet text and
:func:`apply_theme` puts it on a window together with a matching palette, so
the parts Qt draws itself (arrows, check marks, scroll handles) agree with it.
Nothing here loads an image or a font file.
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional

FONT_FAMILY = ('"Segoe UI Variable Text", "Segoe UI", "SF Pro Text", "Helvetica Neue", '
               '"Noto Sans", "Microsoft JhengHei UI", "PingFang TC", "Noto Sans CJK TC", sans-serif')


@dataclass(frozen=True)
class ThemeTokens:
    """Colours and metrics for one theme."""

    name: str
    window: str
    surface: str
    surface_raised: str
    border: str
    text: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_text: str
    selection: str
    hover: str
    danger: str
    radius: int = 6
    spacing: int = 8
    font_family: str = FONT_FAMILY


DARK = ThemeTokens(
    name="dark", window="#16181d", surface="#1d2026", surface_raised="#262a32", border="#343944",
    text="#e7e9ee", text_muted="#9aa1ae", accent="#5b9dff", accent_hover="#7ab0ff", accent_text="#0c1220",
    selection="#2c4470", hover="#2b303a", danger="#ff6b6b",
)
LIGHT = ThemeTokens(
    name="light", window="#f4f5f8", surface="#ffffff", surface_raised="#eceef3", border="#d3d7df",
    text="#1c2029", text_muted="#5f6775", accent="#2563eb", accent_hover="#1d4fd0", accent_text="#ffffff",
    selection="#d4e2ff", hover="#e6e9f0", danger="#c62828",
)
THEMES: Dict[str, ThemeTokens] = {DARK.name: DARK, LIGHT.name: LIGHT}
DEFAULT_THEME = DARK.name


def theme_named(name: str) -> ThemeTokens:
    """Return the theme called ``name``, or the default for an unknown name."""
    return THEMES.get(name, THEMES[DEFAULT_THEME])


def font_rule(point_size: int) -> str:
    """Style sheet rule setting the text size everywhere."""
    return f"* {{ font-size: {int(point_size)}pt; }}"


_TEMPLATE = """
QWidget {{ background-color: {window}; color: {text}; font-family: {font_family}; }}
QMainWindow, QDialog, QDockWidget {{ background-color: {window}; }}
QLabel, QCheckBox, QRadioButton {{ background: transparent; }}
QToolTip {{ background-color: {surface_raised}; color: {text}; border: 1px solid {border};
    padding: {half}px {spacing}px; border-radius: {radius}px; }}

QMenuBar {{ background-color: {window}; border-bottom: 1px solid {border}; padding: 2px {half}px; }}
QMenuBar::item {{ background: transparent; padding: {half}px {spacing}px; border-radius: {radius}px; }}
QMenuBar::item:selected, QMenuBar::item:pressed {{ background-color: {hover}; }}
QMenu {{ background-color: {surface}; border: 1px solid {border}; border-radius: {radius}px; padding: {half}px; }}
QMenu::item {{ padding: {half}px {wide}px {half}px {wide}px; border-radius: {small}px; }}
QMenu::item:selected {{ background-color: {selection}; }}
QMenu::item:disabled {{ color: {text_muted}; }}
QMenu::separator {{ height: 1px; background: {border}; margin: {half}px {spacing}px; }}

QTabWidget::pane {{ border: 1px solid {border}; border-radius: {radius}px; background-color: {surface}; top: -1px; }}
QTabBar {{ background: transparent; qproperty-drawBase: 0; }}
QTabBar::tab {{ background: transparent; color: {text_muted}; padding: {spacing}px {wide}px;
    border: 1px solid transparent; border-top-left-radius: {radius}px; border-top-right-radius: {radius}px;
    margin-right: 2px; }}
QTabBar::tab:hover {{ color: {text}; background-color: {hover}; }}
QTabBar::tab:selected {{ color: {text}; background-color: {surface}; border-color: {border};
    border-bottom: 2px solid {accent}; }}

QPushButton, QToolButton {{ background-color: {surface_raised}; border: 1px solid {border};
    border-radius: {radius}px; padding: {half}px {wide}px; min-height: 20px; }}
QPushButton:hover, QToolButton:hover {{ background-color: {hover}; border-color: {accent}; }}
QPushButton:pressed, QToolButton:pressed {{ background-color: {selection}; }}
QPushButton:default {{ background-color: {accent}; color: {accent_text}; border-color: {accent}; }}
QPushButton:default:hover {{ background-color: {accent_hover}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {text_muted}; background-color: {window}; }}
QTabBar QToolButton {{ padding: 0; min-height: 0; border-radius: {small}px; }}

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateTimeEdit, QTimeEdit {{
    background-color: {surface}; border: 1px solid {border}; border-radius: {radius}px;
    padding: {half}px {spacing}px; selection-background-color: {selection}; selection-color: {text}; }}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus {{ border-color: {accent}; }}
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled {{ color: {text_muted}; }}
QComboBox QAbstractItemView {{ background-color: {surface}; border: 1px solid {border};
    selection-background-color: {selection}; selection-color: {text}; outline: 0; }}

QTreeView, QListView, QTableView {{ background-color: {surface}; alternate-background-color: {window};
    border: 1px solid {border}; border-radius: {radius}px; gridline-color: {border}; outline: 0; }}
QTreeView::item, QListView::item {{ padding: {small}px {half}px; border-radius: {small}px; }}
QTreeView::item:hover, QListView::item:hover, QTableView::item:hover {{ background-color: {hover}; }}
QTreeView::item:selected, QListView::item:selected, QTableView::item:selected {{
    background-color: {selection}; color: {text}; }}
QHeaderView::section {{ background-color: {surface_raised}; color: {text_muted}; border: 0;
    border-bottom: 1px solid {border}; padding: {half}px {spacing}px; }}
QTableCornerButton::section {{ background-color: {surface_raised}; border: 0; }}

QGroupBox {{ border: 1px solid {border}; border-radius: {radius}px; margin-top: {wide}px;
    padding: {spacing}px; background-color: transparent; }}
QGroupBox::title {{ subcontrol-origin: margin; left: {spacing}px; padding: 0 {half}px; color: {text_muted}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle {{ background-color: {border}; border-radius: 4px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background-color: {text_muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QSplitter::handle {{ background-color: {border}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QProgressBar {{ background-color: {surface_raised}; border: 0; border-radius: {small}px; text-align: center; }}
QProgressBar::chunk {{ background-color: {accent}; border-radius: {small}px; }}
QStatusBar {{ background-color: {window}; border-top: 1px solid {border}; color: {text_muted}; }}

#NavigationPanel {{ background-color: {surface}; border-right: 1px solid {border}; }}
#NavigationPanel QTreeWidget {{ background-color: {surface}; border: 0; border-radius: 0; }}
#NavigationPanel QLineEdit {{ background-color: {window}; }}
#NavigationEmpty {{ color: {text_muted}; padding: {wide}px; }}
"""


def build_stylesheet(tokens: ThemeTokens) -> str:
    """Return the Qt style sheet for ``tokens``."""
    values = dict(vars(tokens))
    values.update(half=tokens.spacing // 2, wide=tokens.spacing * 2, small=max(tokens.radius - 2, 2))
    return _TEMPLATE.format(**values).strip()


def _palette(tokens: ThemeTokens) -> Any:
    from PySide6.QtGui import QColor, QPalette
    role = QPalette.ColorRole
    palette = QPalette()
    for target, colour in (
            (role.Window, tokens.window), (role.WindowText, tokens.text), (role.Base, tokens.surface),
            (role.AlternateBase, tokens.window), (role.Text, tokens.text), (role.Button, tokens.surface_raised),
            (role.ButtonText, tokens.text), (role.ToolTipBase, tokens.surface_raised),
            (role.ToolTipText, tokens.text), (role.Highlight, tokens.accent),
            (role.HighlightedText, tokens.accent_text), (role.PlaceholderText, tokens.text_muted),
            (role.Link, tokens.accent), (role.BrightText, tokens.danger)):
        palette.setColor(target, QColor(colour))
    for target in (role.WindowText, role.Text, role.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, target, QColor(tokens.text_muted))
    return palette


def apply_theme(window: Any, tokens: ThemeTokens, point_size: Optional[int] = None) -> str:
    """Style ``window`` with ``tokens``; return the style sheet without the font rule.

    ``point_size`` appends :func:`font_rule`, so the size is set on top of the
    theme instead of replacing it.
    """
    sheet = build_stylesheet(tokens)
    window.setPalette(_palette(tokens))
    window.setStyleSheet(sheet if point_size is None else f"{sheet}\n{font_rule(point_size)}")
    return sheet


def prepare_application(app: Any) -> None:
    """Give ``app`` the Fusion style, which follows the palette on every platform."""
    app.setStyle("Fusion")
