"""Read validated GUI preferences from an injectable per-user QSettings file."""
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSettings

from je_auto_control.gui.theme import DEFAULT_THEME, theme_named


def default_settings() -> QSettings:
    """Resolve the account home at use time so tests can isolate all writes."""
    return QSettings(str(Path.home() / ".je_auto_control" / "gui.ini"), QSettings.Format.IniFormat)


def _integer(settings: QSettings, key: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(settings.value(f"workspace/{key}", default))
    except (TypeError, ValueError, OverflowError):
        return default
    return value if minimum <= value <= maximum else default


@dataclass(frozen=True)
class WorkspacePreferences:
    """Preferences with safe defaults for missing or malformed stored values."""

    theme: str = DEFAULT_THEME
    font_pt: int = 0
    navigation_visible: bool = True
    navigation_width: int = 260

    @classmethod
    def load(cls, settings: QSettings) -> "WorkspacePreferences":
        """Load supported values, rejecting unknown sizes and corrupted data."""
        font = _integer(settings, "font_pt", 0, 0, 20)
        visible = str(settings.value("workspace/navigation_visible", "true")).lower()
        return cls(
            theme=theme_named(str(settings.value("workspace/theme", DEFAULT_THEME))).name,
            font_pt=font if font in (0, 10, 12, 14, 16, 20) else 0,
            navigation_visible=visible not in ("false", "0"),
            navigation_width=_integer(settings, "navigation_width", 260, 200, 1200),
        )
