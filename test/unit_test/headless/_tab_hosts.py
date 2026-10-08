"""Small real widgets that host the main window's tab mixins.

The script and record tabs are mixins of ``AutoControlGUIWidget``. Their run
slots start work off the GUI thread and receive its outcome through signals,
so a ``SimpleNamespace`` stub can no longer stand in for ``self``; building
the whole main window for one slot would be far too much. These hosts carry
exactly what one mixin needs.
"""
from typing import Optional

from PySide6.QtWidgets import QWidget

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._record_tab import RecordTabMixin
from je_auto_control.gui._script_tab import ScriptTabMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper


class ScriptHost(TranslatableMixin, ScriptTabMixin, QWidget):
    """The Script tab alone."""

    def __init__(self) -> None:
        super().__init__()
        self._tr_init()
        self.page = self._build_script_tab()


class RecordHost(TranslatableMixin, RecordTabMixin, QWidget):
    """The Record tab alone, with ``record_data`` as the last recording."""

    def __init__(self, record_data: Optional[list] = None) -> None:
        super().__init__()
        self._tr_init()
        self._record_data = list(record_data or [])
        self.page = self._build_record_tab()

    def _translate(self, key: str) -> str:
        return language_wrapper.translate(key, key)
