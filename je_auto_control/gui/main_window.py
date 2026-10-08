"""Top-level window: menu bar, feature navigation, tabbed workspace, themes, live language switching."""
import sys
from typing import Callable, Optional

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QDockWidget, QFileDialog, QMainWindow, QMenu, QMessageBox, QWidget,
)

from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.gui.main_widget import AutoControlGUIWidget
from je_auto_control.gui.navigation import NavigationPanel
from je_auto_control.gui.theme import (
    THEMES, ThemeTokens, apply_theme, font_rule, prepare_application, theme_named,
)
from je_auto_control.gui.window_settings import WindowSettings, WindowState


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


_THEME_LABELS = {
    "dark": ("menu_view_theme_dark", "Dark"),
    "light": ("menu_view_theme_light", "Light"),
}


class AutoControlGUIUI(QMainWindow):
    """Main window: menu bar, navigation panel and AutoControlGUIWidget (which owns the tabs).

    ``settings`` is where the theme, text size, navigation panel and geometry
    are remembered between runs; the default is the per-user store of
    :mod:`je_auto_control.gui.window_settings`.
    """

    def __init__(self, settings: Optional[WindowSettings] = None) -> None:
        super().__init__()
        self._settings: WindowSettings = settings if settings is not None else WindowSettings()
        self._state: WindowState = self._settings.load()
        self.app_id = _t("application_name", "AutoControlGUI")
        if sys.platform in ["win32", "cygwin", "msys"]:
            from ctypes import windll  # type: ignore[attr-defined]  # reason: win32-only ctypes
            windll.shell32.SetCurrentProcessExplicitAppUserModelID(self.app_id)

        self._user_font_pt: int = self._state.text_size  # 0 means auto-detect from screen
        self._theme_name: str = self._state.theme
        # The theme's style sheet is kept so _apply_font_pt can append the
        # font rule instead of replacing (and thereby wiping) the theme.
        self._theme_stylesheet: str = apply_theme(self, theme_named(self._theme_name))
        self._apply_font_pt(self._user_font_pt)

        self.setWindowTitle(_t("application_name", "AutoControlGUI"))
        self.resize(1280, 800)
        if self._state.geometry:
            self.restoreGeometry(QByteArray(self._state.geometry))

        self.auto_control_gui_widget = AutoControlGUIWidget(parent=self)
        self.setCentralWidget(self.auto_control_gui_widget)
        self._build_navigation()

        self._view_menu: QMenu = None
        self._actions_menu: QMenu = None
        self._tab_actions: list = []
        self._build_menu_bar()
        self.auto_control_gui_widget.tabs_changed.connect(self._rebuild_tabs_menu)
        self.auto_control_gui_widget.tabs_changed.connect(self._refresh_navigation)
        self.auto_control_gui_widget.tabs_changed.connect(self._rebuild_actions_menu)
        self.auto_control_gui_widget.current_tab_changed.connect(
            self._rebuild_actions_menu,
        )
        language_wrapper.add_listener(self._on_language_changed)
        # Left registered, a language switch after the window was destroyed
        # called into the deleted C++ object.
        listener = self._on_language_changed
        self.destroyed.connect(lambda *_args: language_wrapper.remove_listener(listener))

    # --- navigation ----------------------------------------------------------

    def _build_navigation(self) -> None:
        """Dock the searchable feature list on the left of the workspace."""
        self.navigation = NavigationPanel(self)
        self.navigation.feature_activated.connect(self.auto_control_gui_widget.activate_tab)
        self._navigation_dock = QDockWidget(self)
        self._navigation_dock.setObjectName("NavigationDock")
        self._navigation_dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self._navigation_dock.setTitleBarWidget(QWidget(self._navigation_dock))
        self._navigation_dock.setWidget(self.navigation)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._navigation_dock)
        self.resizeDocks([self._navigation_dock], [self._state.navigation_width], Qt.Orientation.Horizontal)
        # Owned by the window, not by a menu: the menu bar is rebuilt on every
        # language switch, and a shortcut on a per-menu action would be
        # registered once more each time.
        self._search_action = QAction(self)
        self._search_action.setShortcut(QKeySequence("Ctrl+K"))
        self._search_action.triggered.connect(self._focus_feature_search)
        self.addAction(self._search_action)
        # Not the dock's toggleViewAction(): Qt disables that one for a dock
        # without the closable feature, and this dock has no title bar to close.
        self._sidebar_action = QAction(self)
        self._sidebar_action.setCheckable(True)
        self._sidebar_action.setShortcut(QKeySequence("Ctrl+B"))
        self._sidebar_action.triggered.connect(self.set_navigation_visible)
        self.addAction(self._sidebar_action)
        self._navigation_dock.visibilityChanged.connect(self._sync_sidebar_action)
        self._navigation_dock.setVisible(self._state.navigation_visible)
        self._sync_sidebar_action()
        self._refresh_navigation()

    def _refresh_navigation(self) -> None:
        self.navigation.set_entries(
            self.auto_control_gui_widget.list_registered_tabs(), _TAB_CATEGORIES,
        )

    def _focus_feature_search(self) -> None:
        """Show the navigation panel and put the cursor in its search box (Ctrl+K)."""
        self.set_navigation_visible(True)
        self.navigation.focus_search()

    def set_navigation_visible(self, visible: bool) -> None:
        """Show or hide the navigation panel (Ctrl+B) and remember the choice."""
        if visible == self._navigation_dock.isHidden():
            # Hiding takes the width with it, so note it while it is still there.
            self.window_state()
            self._navigation_dock.setVisible(bool(visible))
        self._sync_sidebar_action()
        self._remember()

    def _sync_sidebar_action(self, *_args: object) -> None:
        self._sidebar_action.setChecked(not self._navigation_dock.isHidden())

    # --- remembered state ----------------------------------------------------

    def window_state(self) -> WindowState:
        """What would be remembered if the window closed now."""
        state = self._state
        state.theme = self._theme_name
        state.text_size = self._user_font_pt
        state.navigation_visible = not self._navigation_dock.isHidden()
        # A dock that is hidden, or in a window never shown, has no width worth keeping.
        if self.isVisible() and self._navigation_dock.isVisible():
            state.navigation_width = self._navigation_dock.width()
        state.geometry = bytes(self.saveGeometry().data())
        return state

    def _remember(self, *_args: object) -> None:
        self._settings.save(self.window_state())

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802  # reason: Qt override
        """Save the window's look before it goes."""
        self._remember()
        super().closeEvent(event)

    # --- menu construction ---------------------------------------------------

    def _build_menu_bar(self) -> None:
        bar = self.menuBar()
        bar.clear()
        bar.addMenu(self._build_file_menu())
        bar.addMenu(self._build_actions_menu())
        bar.addMenu(self._build_view_menu())
        bar.addMenu(self._build_tools_menu())
        bar.addMenu(self._build_language_menu())
        bar.addMenu(self._build_help_menu())

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
        open_action.triggered.connect(self._on_open_script)
        menu.addAction(open_action)
        menu.addSeparator()
        exit_action = QAction(_t("menu_file_exit", "Exit"), self)
        exit_action.triggered.connect(self.close)
        menu.addAction(exit_action)
        return menu

    def _build_view_menu(self) -> QMenu:
        menu = QMenu(_t("menu_view", "View"), self)
        self._search_action.setText(_t("menu_view_search", "Search Features..."))
        menu.addAction(self._search_action)
        self._sidebar_action.setText(_t("menu_view_sidebar", "Navigation Panel"))
        menu.addAction(self._sidebar_action)
        tabs_menu = menu.addMenu(_t("menu_view_tabs", "Tabs"))
        self._view_menu = tabs_menu
        self._rebuild_tabs_menu()
        menu.addSeparator()
        theme_menu = menu.addMenu(_t("menu_view_theme", "Theme"))
        self._build_theme_menu(theme_menu)
        text_menu = menu.addMenu(_t("menu_view_text_size", "Text Size"))
        self._build_text_size_menu(text_menu)
        return menu

    def _build_theme_menu(self, menu: QMenu) -> None:
        group = QActionGroup(menu)
        group.setExclusive(True)
        for name in THEMES:
            label_key, default_label = _THEME_LABELS.get(name, (name, name.title()))
            action = QAction(_t(label_key, default_label), menu, checkable=True)
            action.setData(name)
            action.setChecked(name == self._theme_name)
            action.triggered.connect(self._on_theme_selected)
            group.addAction(action)
            menu.addAction(action)

    def _on_theme_selected(self) -> None:
        action = self.sender()
        if isinstance(action, QAction) and action.data():
            self.set_theme(str(action.data()))

    def set_theme(self, name: str) -> None:
        """Switch to the theme called ``name`` (``dark`` or ``light``), keeping the text size."""
        tokens = theme_named(name)
        self._theme_name = tokens.name
        # One style sheet change, font rule included: setting the theme and
        # then the theme plus the font rule made Qt restyle every widget twice.
        self._restyle(lambda: self._set_theme_sheet(tokens))
        self._remember()

    def _set_theme_sheet(self, tokens: ThemeTokens) -> None:
        self._theme_stylesheet = apply_theme(self, tokens, self._effective_font_pt(self._user_font_pt))

    def _effective_font_pt(self, pt: int) -> int:
        return pt if pt > 0 else self._detect_auto_font_pt()

    def _restyle(self, apply: Callable[[], object]) -> None:
        """Run a style change with the pages of unselected tabs out of the way (see ``workspace_tabs``)."""
        workspace = getattr(self, "auto_control_gui_widget", None)
        restyle = getattr(getattr(workspace, "tabs", None), "restyle", None)
        if callable(restyle):
            restyle(apply)
        else:
            apply()

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
            action.toggled.connect(self._on_tab_action_toggled)
            sub.addAction(action)
            self._tab_actions.append(action)

    def _build_text_size_menu(self, menu: QMenu) -> None:
        group = QActionGroup(menu)
        group.setExclusive(True)
        for label_key, default_label, pt in _TEXT_SIZE_PRESETS:
            action = QAction(_t(label_key, default_label), menu, checkable=True)
            action.setData(pt)
            action.setChecked(pt == self._user_font_pt)
            action.triggered.connect(self._on_text_size_selected)
            group.addAction(action)
            menu.addAction(action)

    def _detect_auto_font_pt(self) -> int:
        screen = QApplication.primaryScreen()
        if screen is None:
            return 12
        height = screen.geometry().height()
        if height >= 2000:
            return 13
        if height >= 1300:
            return 11
        return 10

    def _apply_font_pt(self, pt: int) -> None:
        """Apply the font size on top of the active theme stylesheet.

        The theme lives in this window's stylesheet, so the font rule is
        appended rather than assigned — assigning would replace (and wipe) the
        theme on startup and on every text-size change. The font family is
        the theme's; only the size is set here.
        """
        sheet = f"{self._theme_stylesheet}\n{font_rule(self._effective_font_pt(pt))}"
        if sheet != self.styleSheet():      # unchanged: nothing to restyle
            self._restyle(lambda: self.setStyleSheet(sheet))

    def _on_text_size_selected(self) -> None:
        action = self.sender()
        if not isinstance(action, QAction):
            return
        data = action.data()
        self.set_text_size(int(data) if data is not None else 0)

    def set_text_size(self, point_size: int) -> None:
        """Use ``point_size`` for all text; 0 follows the screen's height."""
        self._user_font_pt = max(int(point_size), 0)
        self._apply_font_pt(self._user_font_pt)
        self._remember()

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
            action.triggered.connect(self._on_language_selected)
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
        self.auto_control_gui_widget.retranslate()
        self.navigation.retranslate()
        self._refresh_navigation()
        self._build_menu_bar()

    def _on_about(self) -> None:
        QMessageBox.about(
            self, _t("menu_help_about", "About"),
            "AutoControlGUI — cross-platform automation framework.",
        )

    def _start_hotkeys(self) -> None:
        from je_auto_control.utils.hotkey.hotkey_daemon import default_hotkey_daemon
        try:
            default_hotkey_daemon.start()
        except NotImplementedError as error:
            QMessageBox.warning(self, "Error", str(error))
        self.auto_control_gui_widget.sync_engine_tabs()

    def _start_scheduler(self) -> None:
        from je_auto_control.utils.scheduler.scheduler import default_scheduler
        default_scheduler.start()
        self.auto_control_gui_widget.sync_engine_tabs()

    def _start_triggers(self) -> None:
        from je_auto_control.utils.triggers.trigger_engine import (
            default_trigger_engine,
        )
        default_trigger_engine.start()
        self.auto_control_gui_widget.sync_engine_tabs()


if "__main__" == __name__:
    app = QApplication(sys.argv)
    prepare_application(app)
    window = AutoControlGUIUI()
    window.show()
    sys.exit(app.exec())
