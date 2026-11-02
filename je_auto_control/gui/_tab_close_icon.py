"""The cross on a tab's close button, drawn in code and handed to the style sheet.

Qt's tab bar keeps its own close buttons; only what they show changes. A style
sheet can point ``QTabBar::close-button`` at an image but not at a painter, so
the cross is painted here in the theme's colours and written to a small cache
(``~/.je_auto_control/gui_cache/``) the first time a theme is used. No image
ships with the package.

Replacing the buttons with widgets of our own was tried first and dropped: a
process that opened a tab in a shown window and then left through ``os._exit``
(which every GUI probe in the test suite does) died of an access violation in
8 of 70 runs, against 0 of 59 for the stock buttons.
"""
from pathlib import Path
from typing import Any, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger

_SIDE = 16
_SCALES = (1, 2, 3)


def cache_directory() -> Path:
    """Where the drawn crosses are kept, resolved when asked."""
    return Path.home() / ".je_auto_control" / "gui_cache"


def _draw(colour: str, alpha: int, scale: int) -> Any:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QImage, QPainter, QPen
    side = _SIDE * scale
    image = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    stroke = QColor(colour)
    stroke.setAlpha(alpha)
    pen = QPen(stroke, 1.5 * scale)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    inset, far = side * 0.3, side * 0.7
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(pen)
    painter.drawLine(QPointF(inset, inset), QPointF(far, far))
    painter.drawLine(QPointF(far, inset), QPointF(inset, far))
    painter.end()
    return image


def cross_file(colour: str, alpha: int, directory: Optional[Path] = None) -> Optional[Path]:
    """Path of a cross in ``colour`` at ``alpha`` (0-255), drawing it if it is not cached yet.

    Written at 1x, 2x and 3x (``name@2x.png``), which Qt picks by screen
    scale. ``None`` when the cache cannot be written.
    """
    folder = directory if directory is not None else cache_directory()
    base = folder / f"tab_close_{colour.lstrip('#').lower()}_{int(alpha)}.png"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for scale in _SCALES:
            target = base if scale == 1 else base.with_name(f"{base.stem}@{scale}x.png")
            if not target.is_file() and not _draw(colour, alpha, scale).save(str(target), "PNG"):
                raise OSError(f"could not write {target}")
    except OSError as error:
        autocontrol_logger.warning("tab close icon not cached: %r", error)
        return None
    return base


def close_button_rules(tokens: Any, directory: Optional[Path] = None) -> str:
    """Style sheet rules that put the drawn cross on every tab's close button.

    An empty string when the cache cannot be written: the style's own icon
    stays.
    """
    rest = cross_file(tokens.text_muted, 255, directory)
    hover = cross_file(tokens.text, 255, directory)
    if rest is None or hover is None:
        return ""
    return (
        f'QTabBar::close-button {{ image: url("{rest.as_posix()}"); subcontrol-position: right;'
        f' border-radius: {max(tokens.radius - 2, 2)}px; }}\n'
        f'QTabBar::close-button:hover {{ image: url("{hover.as_posix()}"); background-color: {tokens.hover}; }}\n'
        f'QTabBar::close-button:pressed {{ background-color: {tokens.selection}; }}'
    )
