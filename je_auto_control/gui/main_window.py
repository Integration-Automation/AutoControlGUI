"""Top-level window with menu bar, closable tabs, and live language switching."""
import sys

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QMainWindow, QMenu, QMessageBox,
)
from qt_material import QtStyleTools

from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.gui.main_widget import AutoControlGUIWidget


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


class AutoControlGUIUI(QMainWindow, QtStyleTools):
    """Main window: menu bar + AutoControlGUIWidget (which owns the tabs)."""

    def __init__(self) -> None:
        super().__init__()
        self.app_id = _t("application_name", "AutoControlGUI")
        if sys.platform in ["win32", "cygwin", "msys"]:
            from ctypes import windll
            windll.shell32.SetCurrentProcessExplicitAppUserModelID(self.app_id)

        self._user_font_pt: int = 0  # 0 means auto-detect from screen
        self.apply_stylesheet(self, "dark_amber.xml")
        self._apply_font_pt(self._user_font_pt)

        self.setWindowTitle(_t("application_name", "AutoControlGUI"))
        self.resize(1000, 760)

        self.auto_control_gui_widget = AutoControlGUIWidget(parent=self)
        self.setCentralWidget(self.auto_control_gui_widget)

        self._view_menu: QMenu = None
        self._tab_actions: list = []
        self._build_menu_bar()
        self.auto_control_gui_widget.tabs_changed.connect(self._rebuild_tabs_menu)
        language_wrapper.add_listener(self._on_language_changed)

    # --- menu construction ---------------------------------------------------

    def _build_menu_bar(self) -> None:
        bar = self.menuBar()
        bar.clear()
        bar.addMenu(self._build_file_menu())
        bar.addMenu(self._build_view_menu())
        bar.addMenu(self._build_tools_menu())
        bar.addMenu(self._build_language_menu())
        bar.addMenu(self._build_help_menu())

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
        tabs_menu = menu.addMenu(_t("menu_view_tabs", "Tabs"))
        self._view_menu = tabs_menu
        self._rebuild_tabs_menu()
        menu.addSeparator()
        text_menu = menu.addMenu(_t("menu_view_text_size", "Text Size"))
        self._build_text_size_menu(text_menu)
        return menu

    def _rebuild_tabs_menu(self) -> None:
        if self._view_menu is None:
            return
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
            action = QAction(entry["title"], self, checkable=True)
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
            return 16
        if height >= 1300:
            return 14
        return 12

    def _apply_font_pt(self, pt: int) -> None:
        effective = pt if pt > 0 else self._detect_auto_font_pt()
        self.setStyleSheet(f"font-size: {effective}pt; font-family: 'Lato';")

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

    def _start_scheduler(self) -> None:
        from je_auto_control.utils.scheduler.scheduler import default_scheduler
        default_scheduler.start()

    def _start_triggers(self) -> None:
        from je_auto_control.utils.triggers.trigger_engine import (
            default_trigger_engine,
        )
        default_trigger_engine.start()


if "__main__" == __name__:
    app = QApplication(sys.argv)
    window = AutoControlGUIUI()
    window.show()
    sys.exit(app.exec())
