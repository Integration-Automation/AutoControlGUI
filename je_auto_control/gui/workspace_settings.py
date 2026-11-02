"""Read validated GUI preferences from an injectable per-user QSettings file."""
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from PySide6.QtCore import QSettings

from je_auto_control.gui.theme import DEFAULT_THEME
from je_auto_control.utils.config_sync.workspace_preferences import _coerce_preference


def default_settings() -> QSettings:
    """Resolve the account home at use time so tests can isolate all writes."""
    return QSettings(str(Path.home() / ".je_auto_control" / "gui.ini"), QSettings.Format.IniFormat)


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
        defaults = cls()
        values = {key: _coerce_preference(key, settings.value('workspace/' + key, getattr(defaults, key)))
                  for key in ('theme', 'font_pt', 'navigation_visible', 'navigation_width')}
        return cls(
            theme=cast(str, values['theme']), font_pt=cast(int, values['font_pt']),
            navigation_visible=cast(bool, values['navigation_visible']),
            navigation_width=cast(int, values['navigation_width']),
        )
