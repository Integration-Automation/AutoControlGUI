"""Workspace widget: owns the tab bar and the registry of every tab it can open."""
import json
from typing import Any, Dict, List, Optional, Union

from PySide6.QtCore import QTimer, Signal, QObject
from PySide6.QtGui import QKeyEvent, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from je_auto_control.gui._auto_click_tab import AutoClickTabMixin
from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._image_detect_tab import ImageDetectTabMixin
from je_auto_control.gui._record_tab import RecordTabMixin
from je_auto_control.gui._report_tab import ReportTabMixin
from je_auto_control.gui._screenshot_tab import ScreenshotTabMixin
from je_auto_control.gui._script_tab import ScriptTabMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.gui.tab_registry import (
    TAB_SPECS, MenuActions, TabEntry, WidgetFactory, lazy_factory,
)
from je_auto_control.gui.workspace_tabs import WorkspaceTabWidget
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.json.json_file import read_action_json
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

# Kept under its old name: tests and embedders read ``_tab_entries`` rows as this.
_TabEntry = TabEntry


class _WorkerSignals(QObject):
    finished = Signal(str)
    error = Signal(str)


# =============================================================================
# Main Widget
# =============================================================================
class AutoControlGUIWidget(
    TranslatableMixin, AutoClickTabMixin, ScreenshotTabMixin,
    ImageDetectTabMixin, RecordTabMixin, ScriptTabMixin, ReportTabMixin,
    QWidget,
):
    """Owns the QTabWidget and exposes show/hide/list APIs for the menu bar."""

    tabs_changed = Signal()
    current_tab_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tr_init()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self._tab_entries: List[TabEntry] = []

        # Pages scroll inside their tab when the window is smaller than they
        # are; ``tabs.indexOf(entry.widget)`` and friends still speak in pages.
        self.tabs = WorkspaceTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        # Without this the widest page's minimum size is the window's: the
        # Script Builder alone kept the window from going under ~860 px.
        self.tabs.setMinimumSize(360, 240)
        self.tabs.tabCloseRequested.connect(self._on_tab_close_requested)

        # The window opens on record / script_builder / remote_desktop, with
        # Record in front. Every tab but this widget's own forms is registered
        # without being built: its module is imported and its widget
        # constructed the first time it is on screen, which for the two other
        # start tabs is the first click on them.
        own_tabs = self._own_tab_builders()
        for spec in TAB_SPECS:
            builder, actions = own_tabs.get(spec.key, (None, ()))
            self._add_tab(spec.key, spec.title_key,
                          builder or lazy_factory(spec.module, spec.class_name),
                          category=spec.category, default_visible=spec.default_visible, actions=actions,
                          scrollable=spec.scrollable)
        layout.addWidget(self.tabs)

        self.setLayout(layout)

        self._build_current_tab()
        self.tabs.currentChanged.connect(self._on_current_tab_changed)

        self.timer = QTimer()
        self.repeat_count = 0
        self.repeat_max = 0
        self._record_data = []

    def _own_tab_builders(self) -> Dict[str, Any]:
        """Tabs this widget builds itself: ``key -> (builder, menu actions)``.

        The mixin tabs are built now, not on first open: their builders create
        attributes other slots read (``script_path_input``, the record status
        label), and they are plain forms with nothing running behind them.
        """
        return {
            "auto_click": (self._build_auto_click_tab(), (
                ("start", self._start_auto_click),
                ("stop", self._stop_auto_click),
                ("get_position", self._get_mouse_pos),
                ("hotkey_send", self._send_hotkey),
                ("write_send", self._send_write),
                ("scroll_send", self._send_scroll),
            )),
            "screenshot": (self._build_screenshot_tab(), (
                ("take_screenshot", self._take_screenshot),
                ("browse", self._browse_ss_path),
                ("pick_region", self._pick_ss_region),
                ("get_screen_size", self._get_screen_size),
                ("get_pixel_label", self._get_pixel_color),
            )),
            "image_detect": (self._build_image_detect_tab(), (
                ("browse", self._browse_img),
                ("crop_template", self._crop_template),
                ("locate_image", self._locate_image),
                ("locate_all", self._locate_all),
                ("locate_click", self._locate_click),
            )),
            "record": (self._build_record_tab(), (
                ("start_record", self._start_record),
                ("stop_record", self._stop_record),
                ("playback", self._playback_record),
                ("save_record", self._save_record),
                ("load_record", self._load_record),
            )),
            "script": (self._build_script_tab(), (
                ("load_script", self._browse_script),
                ("execute_script", self._execute_script),
                ("menu_choose_script_dir", self._browse_script_dir),
                ("execute_dir", self._execute_dir),
                ("execute_editor_script", self._execute_manual_script),
            )),
            "remote_desktop": (self._build_remote_desktop_tab, ()),
            "report": (self._build_report_tab(), (
                ("enable_test_record", self._enable_test_record),
                ("disable_test_record", self._disable_test_record),
                ("generate_html_report", self._gen_html),
                ("generate_json_report", self._gen_json),
                ("generate_xml_report", self._gen_xml),
            )),
        }

    @staticmethod
    def _build_remote_desktop_tab() -> QWidget:
        """Return the real remote-desktop tab, or a placeholder if the
        ``webrtc`` extra is not installed.

        Remote desktop relies on the optional ``webrtc`` extra (aiortc + PyAV);
        embedders such as PyBreeze install je_auto_control without it, so a
        failed import becomes a tab that says how to enable it.
        """
        try:
            from je_auto_control.gui.remote_desktop_tab import RemoteDesktopTab
        except ImportError as error:
            import_error: ImportError = error
        else:
            return RemoteDesktopTab()
        placeholder = QWidget()
        layout = QVBoxLayout(placeholder)
        message = QLabel(
            "Remote Desktop is unavailable: the optional 'webrtc' extra "
            "(aiortc + PyAV) is not installed.\n\n"
            "Install with:\n    pip install je_auto_control[webrtc]\n\n"
            f"Underlying error: {import_error!r}",
        )
        message.setWordWrap(True)
        message.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(message)
        layout.addStretch()
        return placeholder

    # --- tab registry API ----------------------------------------------------

    def _add_tab(
            self, key: str, title_key: str, widget: Union[QWidget, WidgetFactory],
            category: str = "core", default_visible: bool = False,
            actions: MenuActions = (), scrollable: bool = True,
    ) -> None:
        """Register a tab from a widget, or from a factory called the first time it is on screen."""
        title = language_wrapper.translate(title_key, title_key)
        if isinstance(widget, QWidget):
            built = widget
            entry = TabEntry(key=key, title_key=title_key, factory=lambda: built,
                             category=category, default_visible=default_visible, actions=actions,
                             scrollable=scrollable, releasable=False)
            self._tab_entries.append(entry)
            if default_visible:
                self.tabs.addTab(entry.widget, title, scrollable=scrollable)
            else:
                AutoControlGUIWidget._adopt_hidden_tab(self, entry.widget)
            return
        entry = TabEntry(key=key, title_key=title_key, factory=widget,
                         category=category, default_visible=default_visible, actions=actions,
                         scrollable=scrollable,
                         on_build=lambda page: AutoControlGUIWidget._place_built_tab(self, key, page))
        self._tab_entries.append(entry)
        if default_visible:
            self.tabs.insert_deferred_tab(self.tabs.count(), key, title, scrollable)

    def _place_built_tab(self, key: str, page: QWidget) -> None:
        """Put a page built just now where it belongs: its waiting tab, or kept hidden."""
        if not self.tabs.fill_deferred(key, page):
            AutoControlGUIWidget._adopt_hidden_tab(self, page)

    def _build_current_tab(self) -> None:
        """Build the selected tab's page if it is still waiting for its first show."""
        key = self.tabs.deferred_key(self.tabs.currentIndex())
        entry = self._find_entry(key) if key else None
        if entry is not None:
            _ = entry.widget

    def _adopt_hidden_tab(self, widget: QWidget) -> None:
        # Owned from the start: an unparented hidden tab outlived this
        # widget, and one a registry held a listener of (Presence) kept
        # its timer running after every window that built it was gone.
        if self.tabs.indexOf(widget) == -1:
            widget.setParent(self)
            widget.hide()

    @staticmethod
    def _is_built(entry: Any) -> bool:
        return bool(getattr(entry, "built", True))

    def _built_entries(self) -> List[Any]:
        return [entry for entry in self._tab_entries if self._is_built(entry)]

    def _tab_index(self, entry: Any) -> int:
        """Where ``entry`` is in the tab bar, or -1; never builds the tab."""
        if self._is_built(entry):
            return int(self.tabs.indexOf(entry.widget))
        return int(self.tabs.index_of_deferred(entry.key))

    def _is_open(self, entry: Any) -> bool:
        return self._tab_index(entry) != -1

    def _on_current_tab_changed(self, _index: int) -> None:
        self._build_current_tab()
        self.current_tab_changed.emit()

    def current_tab_menu_actions(self) -> list:
        """Return ``[(label_key, callable), ...]`` for the active tab.

        Core tabs declare their actions at registration time; feature tabs
        may instead expose a ``menu_actions()`` method returning the same
        shape. The menu bar renders these under the Actions menu so tabs
        stay button-free.
        """
        widget = self.tabs.currentWidget()
        if widget is None:
            return []
        for entry in self._built_entries():
            if entry.widget is widget:
                if entry.actions:
                    return list(entry.actions)
                provider = getattr(widget, "menu_actions", None)
                if callable(provider):
                    return list(provider())
                return []
        return []

    def _find_entry(self, key: str):
        for entry in self._tab_entries:
            if entry.key == key:
                return entry
        return None

    def sync_engine_tabs(self) -> None:
        """Let every built tab that mirrors an engine re-read its state (after Tools > Start).

        A tab not built yet reads the engine when it is.
        """
        for entry in self._tab_entries:
            if not AutoControlGUIWidget._is_built(entry):
                continue
            sync = getattr(entry.widget, "sync_with_engine", None)
            if callable(sync):
                sync()

    def list_registered_tabs(self) -> list:
        """Return metadata for the View → Tabs menu and the navigation panel.

        Reading it builds nothing: a tab never opened is listed as not visible.
        """
        return [
            {
                "key": entry.key,
                "title": language_wrapper.translate(entry.title_key, entry.title_key),
                "visible": self._is_open(entry),
                "category": entry.category,
            }
            for entry in self._tab_entries
        ]

    def current_tab_key(self) -> Optional[str]:
        """Key of the tab on screen, or ``None`` when every tab is closed."""
        widget = self.tabs.currentWidget()
        for entry in self._built_entries():
            if entry.widget is widget:
                return str(entry.key)
        return None

    def show_tab(self, key: str) -> None:
        """Open the tab ``key`` (building it if this is its first time) and select it."""
        entry = self._find_entry(key)
        if entry is None or self._is_open(entry):
            return
        target_index = 0
        for candidate in self._tab_entries:
            if candidate.key == key:
                break
            if self._is_open(candidate):
                target_index += 1
        title = language_wrapper.translate(entry.title_key, entry.title_key)
        self.tabs.insertTab(target_index, entry.widget, title, scrollable=entry.scrollable)
        self.tabs.setCurrentWidget(entry.widget)
        self.tabs_changed.emit()

    def open_tab(self, key: str) -> Optional[QWidget]:
        """Open and select the tab ``key``; return its widget, or ``None`` for an unknown key."""
        entry = self._find_entry(key)
        if entry is None:
            return None
        self.activate_tab(key)
        widget: QWidget = entry.widget
        return widget

    def close_tab(self, key: str, release: bool = False) -> bool:
        """Close the tab ``key``; with ``release`` also let go of its widget.

        Without ``release`` this is :meth:`hide_tab`: the widget is kept and
        the next open shows it as it was left. With it, the widget's optional
        ``dispose()`` is called and the widget deleted, so what it held
        (timers, threads, listeners) goes with it and the next open builds a
        new one. Returns whether a widget was released; the forms this widget
        builds for itself are never released.
        """
        entry = self._find_entry(key)
        if entry is None:
            return False
        self.hide_tab(key)
        if not release:
            return False
        try:
            return bool(entry.release())
        except Exception as error:  # noqa: BLE001  # reason: a failing dispose() must not undo the release
            autocontrol_logger.error("dispose() of tab %s failed: %r", key, error)
            return True

    def activate_tab(self, key: str) -> bool:
        """Bring the tab ``key`` to the front, opening it first if needed."""
        entry = self._find_entry(key)
        if entry is None:
            return False
        if self._is_open(entry):
            self.tabs.setCurrentIndex(self._tab_index(entry))
        else:
            self.show_tab(key)
        return True

    def hide_tab(self, key: str) -> None:
        """Close the tab ``key``; its widget is kept for the next time it is opened."""
        entry = self._find_entry(key)
        if entry is None:
            return
        index = self._tab_index(entry)
        if index != -1:
            self.tabs.removeTab(index)
            self.tabs_changed.emit()

    def _on_tab_close_requested(self, index: int) -> None:
        waiting = self.tabs.deferred_key(index)
        if waiting:
            self.hide_tab(waiting)
            return
        widget = self.tabs.widget(index)
        for entry in self._built_entries():
            if entry.widget is widget:
                self.hide_tab(entry.key)
                return

    def _translate(self, key: str) -> str:
        return language_wrapper.translate(key, key)

    def retranslate(self) -> None:
        """Relabel tab titles and propagate into every child tab."""
        for entry in self._tab_entries:
            index = self._tab_index(entry)
            if index != -1:
                self.tabs.setTabText(
                    index, language_wrapper.translate(entry.title_key, entry.title_key),
                )
        # Widgets registered via TranslatableMixin on this widget (screenshot,
        # image-detect, record, script, screen-record, shell, report tabs).
        TranslatableMixin.retranslate(self)
        if hasattr(self, "_auto_click_retranslate"):
            self._auto_click_retranslate()
        if hasattr(self, "_screenshot_retranslate"):
            self._screenshot_retranslate()
        if hasattr(self, "_record_retranslate"):
            self._record_retranslate()
        # Child class tabs get their own retranslate if they implement one.
        for entry in self._built_entries():
            callback = getattr(entry.widget, "retranslate", None)
            if callable(callback) and entry.widget is not self:
                try:
                    callback()
                except (RuntimeError, AttributeError):
                    continue

    def open_script_file(self, path: str) -> None:
        """Load a JSON script into the Script Executor tab and focus it."""
        entry = self._find_entry("script")
        if entry is not None and not self._is_open(entry):
            self.show_tab("script")
        self.script_path_input.setText(path)
        try:
            data = read_action_json(path)
            self.script_editor.setText(json.dumps(data, indent=2, ensure_ascii=False))
        except (AutoControlException, OSError, ValueError, TypeError, RuntimeError) as error:
            self.script_result_text.setText(f"Error loading: {error}")
            return
        if entry is not None:
            self.tabs.setCurrentWidget(entry.widget)

    # =========================================================================
    # Global keyboard shortcut: Ctrl+4 to stop
    # =========================================================================
    def keyPressEvent(self, event: QKeyEvent):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_4:
            self._stop_auto_click()
        else:
            super().keyPressEvent(event)
