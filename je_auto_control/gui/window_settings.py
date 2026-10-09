"""What the main window remembers between runs, and where it is kept.

Theme, text size, the navigation panel's visibility and width, and the window
geometry are written to one INI file through ``QSettings``:
``~/.je_auto_control/gui_settings.ini``, resolved when it is used, so a
redirected home directory moves it like the rest of the per-user state.
``JE_AUTOCONTROL_GUI_SETTINGS`` names another file, or switches the store off
(``off``, ``0``, ``none``, ``false`` or empty): nothing is read and nothing is
written, which is what the test suite runs with.

A tab may also keep the text of its form fields there
(:meth:`WindowSettings.load_form` / :meth:`WindowSettings.save_form`), under
``[forms]`` and its own name. That is for what a user would otherwise retype on
every start -- a server address, a folder -- and never for a credential: the
file is plain text, and the tab chooses which fields it hands over.
"""
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from PySide6.QtCore import QByteArray, QSettings

from je_auto_control.gui.theme import DEFAULT_THEME, THEMES
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

SETTINGS_ENV = "JE_AUTOCONTROL_GUI_SETTINGS"
DEFAULT_NAVIGATION_WIDTH = 260
_OFF_VALUES = frozenset({"", "off", "0", "none", "false"})
_WIDTH_RANGE = (200, 800)
_TEXT_SIZE_RANGE = (6, 48)
_GROUP = "main_window"
_FORMS_GROUP = "forms"
_FORM_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}")
#: A remembered field longer than this was not typed into a one-line input.
_FORM_VALUE_LIMIT = 2048
_UNSET: Any = object()


def settings_path() -> Optional[Path]:
    """The settings file in force, or ``None`` when the store is switched off."""
    value = os.environ.get(SETTINGS_ENV)
    if value is None:
        return Path.home() / ".je_auto_control" / "gui_settings.ini"
    if value.strip().lower() in _OFF_VALUES:
        return None
    return Path(os.path.realpath(os.path.expanduser(value.strip())))


@dataclass
class WindowState:
    """The remembered look of the main window; the defaults are a first run."""

    theme: str = DEFAULT_THEME
    text_size: int = 0
    navigation_visible: bool = True
    navigation_width: int = DEFAULT_NAVIGATION_WIDTH
    geometry: bytes = b""


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return default


def _as_int(value: Any, default: int, bounds: Tuple[int, int]) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if bounds[0] <= number <= bounds[1] else default


def _as_bytes(value: Any) -> bytes:
    if isinstance(value, QByteArray):
        return bytes(value.data())
    return bytes(value) if isinstance(value, (bytes, bytearray)) else b""


class WindowSettings:
    """Load and save a :class:`WindowState`; a store without a path does neither."""

    def __init__(self, path: str | Path | None = _UNSET) -> None:
        resolved = settings_path() if path is _UNSET else path
        self._path: Optional[Path] = None if resolved is None else Path(resolved)

    @property
    def path(self) -> Optional[Path]:
        """The INI file, or ``None`` when nothing is persisted."""
        return self._path

    def _open(self) -> QSettings:
        return QSettings(str(self._path), QSettings.Format.IniFormat)

    def load(self) -> WindowState:
        """Return what was saved; anything missing or out of range is the default."""
        state = WindowState()
        if self._path is None or not self._path.is_file():
            return state
        store = self._open()
        store.beginGroup(_GROUP)
        theme = str(store.value("theme", state.theme))
        state.theme = theme if theme in THEMES else state.theme
        # 0 is "follow the screen"; anything else has to be a plausible point size.
        state.text_size = _as_int(store.value("text_size", 0), 0, _TEXT_SIZE_RANGE)
        state.navigation_visible = _as_bool(store.value("navigation_visible", True), True)
        state.navigation_width = _as_int(
            store.value("navigation_width", DEFAULT_NAVIGATION_WIDTH), DEFAULT_NAVIGATION_WIDTH, _WIDTH_RANGE)
        state.geometry = _as_bytes(store.value("geometry", QByteArray()))
        store.endGroup()
        return state

    def save(self, state: WindowState) -> bool:
        """Write ``state``; return whether it reached the file."""
        if self._path is None:
            return False
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            autocontrol_logger.warning("GUI settings not saved to %s: %r", self._path, error)
            return False
        store = self._open()
        store.beginGroup(_GROUP)
        store.setValue("theme", state.theme)
        store.setValue("text_size", int(state.text_size))
        store.setValue("navigation_visible", bool(state.navigation_visible))
        store.setValue("navigation_width", int(state.navigation_width))
        store.setValue("geometry", QByteArray(state.geometry))
        store.endGroup()
        return self._commit(store)

    def _commit(self, store: QSettings) -> bool:
        store.sync()
        if store.status() != QSettings.Status.NoError:
            autocontrol_logger.warning("GUI settings not saved to %s: %s", self._path, store.status())
            return False
        return True

    @staticmethod
    def _form_group(name: str) -> str:
        if not _FORM_NAME.fullmatch(name):
            raise ValueError(f"form name must be letters, digits and underscores, got {name!r}")
        return f"{_FORMS_GROUP}/{name}"

    def load_form(self, name: str) -> Dict[str, str]:
        """Return the fields remembered for the form ``name``; empty when none were saved.

        Only well-formed field names with plain, short text come back: the
        file is user-editable, and a value from it goes into an input as is.
        """
        group = self._form_group(name)
        if self._path is None or not self._path.is_file():
            return {}
        store = self._open()
        store.beginGroup(group)
        fields: Dict[str, str] = {}
        for key in store.childKeys():
            value = store.value(key)
            if _FORM_NAME.fullmatch(key) and isinstance(value, str) and len(value) <= _FORM_VALUE_LIMIT:
                fields[key] = value
        store.endGroup()
        return fields

    def save_form(self, name: str, fields: Mapping[str, str]) -> bool:
        """Remember ``fields`` for the form ``name``, replacing what was saved; return whether it was written.

        Never pass a secret: this is a plain-text file.
        """
        group = self._form_group(name)
        for key in fields:
            if not _FORM_NAME.fullmatch(key):
                raise ValueError(f"field name must be letters, digits and underscores, got {key!r}")
        if self._path is None:
            return False
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            autocontrol_logger.warning("GUI settings not saved to %s: %r", self._path, error)
            return False
        store = self._open()
        store.beginGroup(group)
        store.remove("")                # this form's old fields only
        for key, value in fields.items():
            store.setValue(key, str(value)[:_FORM_VALUE_LIMIT])
        store.endGroup()
        return self._commit(store)
