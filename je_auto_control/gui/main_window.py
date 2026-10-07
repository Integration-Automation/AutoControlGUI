"""Top-level window with menu bar, closable tabs, and live language switching."""
import sys
from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QMainWindow, QMenu, QMessageBox,
)

from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.gui.main_widget import AutoControlGUIWidget
from je_auto_control.gui.theme import ThemeTokens, apply_theme
from je_auto_control.gui.workspace import WorkspaceShell


def _t(key: str, default: str = "") -> str:
    return language_wrapper.translate(key, default or key)


_TAB_CATEGORIES = (
    ("core", "menu_view_cat_core", "Core"),
    ("editing", "menu_view_cat_editing", "Editing"),
    ("detection", "menu_view_cat_detection", "Detection & Vision"),
    ("automation", "menu_view_cat_automation", "Automation Engines"),
    ("system", "menu_view_cat_system", "System"),
)

_TEXT_SIZE_PRESETS = (
    ("menu_view_text_auto", "Auto", 0),
    ("menu_view_text_small", "Small", 10),
    ("menu_view_text_normal", "Normal", 12),
    ("menu_view_text_large", "Large", 14),
    ("menu_view_text_xlarge", "Extra Large", 16),
    ("menu_view_text_xxlarge", "Huge", 20),
)


class AutoControlGUIUI(QMainWindow):  # pylint: disable=too-many-instance-attributes  # reason: independent menus, theme, registry and window state
    """Main window: menu bar + AutoControlGUIWidget (which owns the tabs)."""

    def __init__(self) -> None:
        super().__init__()
        self.app_id = _t("application_name", "AutoControlGUI")
        if sys.platform in ["win32", "cygwin", "msys"]:
            # pylint: disable-next=import-outside-toplevel  # reason: platform or selected engine is loaded on demand
            from ctypes import windll  # type: ignore[attr-defined]  # reason: win32-only ctypes
            windll.shell32.SetCurrentProcessExplicitAppUserModelID(self.app_id)

        self._user_font_pt: int = 0  # 0 means auto-detect from screen
        self._theme = ThemeTokens.dark()
        apply_theme(self, self._theme)
        self._theme_stylesheet: str = self.styleSheet()
        self._apply_font_pt(self._user_font_pt)

        self.setWindowTitle(_t("application_name", "AutoControlGUI"))
        self.resize(1000, 760)

        self.auto_control_gui_widget = AutoControlGUIWidget(parent=self)
        self.workspace_shell = WorkspaceShell(self.auto_control_gui_widget.registry, parent=self)
        self.setCentralWidget(self.workspace_shell)
        self._apply_font_pt(self._user_font_pt)

        self._view_menu: QMenu = None
        self._actions_menu: QMenu = None
        self._tab_actions: list = []
        self._build_menu_bar()
        self.auto_control_gui_widget.tabs_changed.connect(self._rebuild_tabs_menu)
        self.auto_control_gui_widget.tabs_changed.connect(self._rebuild_actions_menu)
        self.auto_control_gui_widget.current_tab_changed.connect(
            self._rebuild_actions_menu,
        )
        language_wrapper.add_listener(self._on_language_changed)
        # Left registered, a language switch after the window was destroyed
        # called into the deleted C++ object.
        listener = self._on_language_changed
        self.destroyed.connect(  # pylint: disable=no-member  # reason: Qt SignalInstance runtime binding
            lambda *_args: language_wrapper.remove_listener(listener))

    # --- menu construction ---------------------------------------------------

    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()
        menu_bar.clear()
        menu_bar.addMenu(self._build_file_menu())
        menu_bar.addMenu(self._build_actions_menu())
        menu_bar.addMenu(self._build_view_menu())
        menu_bar.addMenu(self._build_tools_menu())
        menu_bar.addMenu(self._build_language_menu())
        menu_bar.addMenu(self._build_help_menu())

    def _build_actions_menu(self) -> QMenu:
        """Per-tab command menu: the active tab's operations live here
        instead of as buttons inside the tab."""
        self._actions_menu = QMenu(_t("menu_actions", "Actions"), self)
        self._rebuild_actions_menu()
        return self._actions_menu

    def _rebuild_actions_menu(self) -> None:
        if self._actions_menu is None:
            return
        self._actions_menu.clear()
        entries = self.auto_control_gui_widget.current_tab_menu_actions()
        if not entries:
            placeholder = QAction(
                _t("menu_actions_none", "(No actions on this tab)"), self,
            )
            placeholder.setEnabled(False)
            self._actions_menu.addAction(placeholder)
            return
        for label_key, handler in entries:
            self._actions_menu.addAction(_t(label_key, label_key), handler)

    def _build_file_menu(self) -> QMenu:
        menu = QMenu(_t("menu_file", "File"), self)
        open_action = QAction(_t("menu_file_open_script", "Open Script..."), self)
        open_action.triggered.connect(self._on_open_script)  # pylint: disable=no-member  # reason: Qt SignalInstance runtime binding
        menu.addAction(open_action)
        menu.addSeparator()
        exit_action = QAction(_t("menu_file_exit", "Exit"), self)
        exit_action.triggered.connect(self.close)  # pylint: disable=no-member  # reason: Qt SignalInstance runtime binding
        menu.addAction(exit_action)
        return menu

    def _build_view_menu(self) -> QMenu:
        menu = QMenu(_t("menu_view", "View"), self)
        tabs_menu = menu.addMenu(_t("menu_view_tabs", "Tabs"))
        self._view_menu = tabs_menu
        self._rebuild_tabs_menu()
        menu.addSeparator()
        text_menu = menu.addMenu(_t("menu_view_text_size", "Text Size"))
        self._build_text_size_menu(text_menu)
        theme_menu = menu.addMenu(_t('workspace_theme', 'Theme'))
        theme_menu.addAction(_t('workspace_theme_dark', 'Dark'), lambda: self._set_theme(False))
        theme_menu.addAction(_t('workspace_theme_light', 'Light'), lambda: self._set_theme(True))
        menu.addAction(_t('workspace_details_toggle', 'Execution details'), self.workspace_shell.toggle_details)
        return menu

    def _set_theme(self, light: bool) -> None:
        self._theme = ThemeTokens.light() if light else ThemeTokens.dark()
        self._apply_font_pt(self._user_font_pt)

    def _rebuild_tabs_menu(self) -> None:
        if self._view_menu is None:
            return
        # clear() only detaches: the submenus (and, parented to them, their
        # actions) stayed alive, 51 more actions and a menu per rebuild.
        for submenu in self._view_menu.findChildren(QMenu, options=Qt.FindChildOption.FindDirectChildrenOnly):
            submenu.deleteLater()
        self._view_menu.clear()
        self._tab_actions = []
        entries_by_cat: dict = {}
        for entry in self.auto_control_gui_widget.list_registered_tabs():
            entries_by_cat.setdefault(entry["category"], []).append(entry)
        for cat_key, title_key, default in _TAB_CATEGORIES:
            entries = entries_by_cat.pop(cat_key, [])
            if entries:
                self._add_category_submenu(_t(title_key, default), entries)
        for cat_key, entries in entries_by_cat.items():
            if entries:
                self._add_category_submenu(cat_key.title(), entries)

    def _add_category_submenu(self, label: str, entries: list) -> None:
        sub = self._view_menu.addMenu(label)
        for entry in entries:
            action = QAction(entry["title"], sub, checkable=True)
            action.setChecked(entry["visible"])
            action.setData(entry["key"])
            action.toggled.connect(self._on_tab_action_toggled)  # pylint: disable=no-member  # reason: Qt SignalInstance runtime binding
            sub.addAction(action)
            self._tab_actions.append(action)

    def _build_text_size_menu(self, menu: QMenu) -> None:
        group = QActionGroup(menu)
        group.setExclusive(True)
        for label_key, default_label, pt in _TEXT_SIZE_PRESETS:
            action = QAction(_t(label_key, default_label), menu, checkable=True)
            action.setData(pt)
            action.setChecked(pt == self._user_font_pt)
            action.triggered.connect(self._on_text_size_selected)  # pylint: disable=no-member  # reason: Qt SignalInstance runtime binding
            group.addAction(action)
            menu.addAction(action)

    def _detect_auto_font_pt(self) -> int:
        screen = QApplication.primaryScreen()
        if screen is None:
            return 12
        height = screen.geometry().height()
        if height >= 2000:
            return 16
        if height >= 1300:
            return 14
        return 12

    def _apply_font_pt(self, pt: int) -> None:
        """Change system-font size while preserving the active palette and focus rules."""
        effective = pt if pt > 0 else self._detect_auto_font_pt()
        theme = getattr(self, '_theme', None)
        if isinstance(theme, ThemeTokens):
            self._theme = replace(theme, font_point_size=effective)
            apply_theme(self, self._theme)
            if hasattr(self, 'workspace_shell'):
                apply_theme(self.workspace_shell, self._theme)
            self._theme_stylesheet = self.styleSheet()
        else:
            # Keep the existing unbound font helper contract for Qt embedders.
            self.setStyleSheet(f"{self._theme_stylesheet}\n* {{ font-size: {effective}pt; }}")

    def _on_text_size_selected(self) -> None:
        action = self.sender()
        if not isinstance(action, QAction):
            return
        data = action.data()
        self._user_font_pt = int(data) if data is not None else 0
        self._apply_font_pt(self._user_font_pt)

    def _on_tab_action_toggled(self, checked: bool) -> None:
        action = self.sender()
        if not isinstance(action, QAction):
            return
        key = action.data()
        if checked:
            self.auto_control_gui_widget.show_tab(key)
        else:
            self.auto_control_gui_widget.hide_tab(key)

    def _build_tools_menu(self) -> QMenu:
        menu = QMenu(_t("menu_tools", "Tools"), self)
        menu.addAction(
            _t("menu_tools_start_hotkeys", "Start hotkey daemon"),
            self._start_hotkeys,
        )
        menu.addAction(
            _t("menu_tools_start_scheduler", "Start scheduler"),
            self._start_scheduler,
        )
        menu.addAction(
            _t("menu_tools_start_triggers", "Start trigger engine"),
            self._start_triggers,
        )
        return menu

    def _build_language_menu(self) -> QMenu:
        menu = QMenu(_t("menu_language", "Language"), self)
        group = QActionGroup(menu)
        group.setExclusive(True)
        for lang in language_wrapper.available_languages:
            action = QAction(lang.replace("_", " "), menu, checkable=True)
            action.setData(lang)
            action.setChecked(lang == language_wrapper.language)
            action.triggered.connect(self._on_language_selected)  # pylint: disable=no-member  # reason: Qt SignalInstance runtime binding
            group.addAction(action)
            menu.addAction(action)
        return menu

    def _build_help_menu(self) -> QMenu:
        menu = QMenu(_t("menu_help", "Help"), self)
        menu.addAction(
            _t("menu_help_about", "About AutoControlGUI"), self._on_about,
        )
        return menu

    # --- actions -------------------------------------------------------------

    def _on_open_script(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, _t("menu_file_open_script", "Open Script"), "", "JSON (*.json)",
        )
        if path:
            self.auto_control_gui_widget.open_script_file(path)

    def _on_language_selected(self) -> None:
        action = self.sender()
        if not isinstance(action, QAction):
            return
        language_wrapper.reset_language(action.data())

    def _on_language_changed(self, _language: str) -> None:
        self.setWindowTitle(_t("application_name", "AutoControlGUI"))
        self.workspace_shell.retranslate()
        self._build_menu_bar()

    def _on_about(self) -> None:
        QMessageBox.about(
            self, _t("menu_help_about", "About"),
            "AutoControlGUI — cross-platform automation framework.",
        )

    def closeEvent(self, event: QCloseEvent) -> None:  # pylint: disable=invalid-name  # reason: Qt virtual callback
        """Close constructed workflow owners before the top-level window is hidden."""
        self.workspace_shell.close()
        super().closeEvent(event)

    def _start_hotkeys(self) -> None:
        # pylint: disable-next=import-outside-toplevel  # reason: platform or selected engine is loaded on demand
        from je_auto_control.utils.hotkey.hotkey_daemon import default_hotkey_daemon
        try:
            default_hotkey_daemon.start()
        except NotImplementedError as error:
            QMessageBox.warning(self, "Error", str(error))
        self.auto_control_gui_widget.sync_engine_tabs()

    def _start_scheduler(self) -> None:
        # pylint: disable-next=import-outside-toplevel  # reason: platform or selected engine is loaded on demand
        from je_auto_control.utils.scheduler.scheduler import default_scheduler
        default_scheduler.start()
        self.auto_control_gui_widget.sync_engine_tabs()

    def _start_triggers(self) -> None:
        # pylint: disable-next=import-outside-toplevel  # reason: platform or selected engine is loaded on demand
        from je_auto_control.utils.triggers.trigger_engine import (
            default_trigger_engine,
        )
        default_trigger_engine.start()
        self.auto_control_gui_widget.sync_engine_tabs()


if "__main__" == __name__:
    app = QApplication(sys.argv)
    window = AutoControlGUIUI()
    window.show()
    sys.exit(app.exec())
