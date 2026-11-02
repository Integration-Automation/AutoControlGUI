"""Workspace overflow and preferences survive resize and a fresh window."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    widgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    return widgets.QApplication.instance() or widgets.QApplication([])


@pytest.fixture
def window_factory(qapp, monkeypatch, tmp_path):
    from PySide6.QtCore import QSettings
    from je_auto_control.gui import main_widget
    from je_auto_control.gui.main_window import AutoControlGUIUI

    # These real forms exercise the shell without starting native network helpers.
    monkeypatch.setattr(main_widget, "TAB_SPECS", tuple(
        spec for spec in main_widget.TAB_SPECS if spec.key in {"record", "variables", "auto_click"}
    ))
    settings = QSettings(str(tmp_path / "workspace.ini"), QSettings.Format.IniFormat)
    windows = []

    def build():
        window = AutoControlGUIUI(settings=settings)
        windows.append(window)
        window.show()
        qapp.processEvents()
        return window

    yield build, settings
    for window in windows:
        window.close()
        window.deleteLater()


def test_narrow_content_scrolls_without_changing_the_tab_widget_contract(qapp):
    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
    from je_auto_control.gui.workspace import ScrollableTabs

    tabs = ScrollableTabs()
    page = QWidget()
    layout = QVBoxLayout(page)
    label = QLabel("far corner")
    label.setMinimumSize(900, 650)
    layout.addWidget(label)
    other = QWidget()
    tabs.addTab(page, "Wide")
    tabs.addTab(other, "Other")
    tabs.resize(360, 240)
    tabs.show()
    qapp.processEvents()
    try:
        assert tabs.indexOf(page) == 0
        assert tabs.widget(0) is page and tabs.currentWidget() is page
        scroll = tabs.scroll_area(0)
        assert scroll.widget() is page
        assert scroll.horizontalScrollBar().maximum() > 0
        assert scroll.verticalScrollBar().maximum() > 0
        scroll.ensureVisible(page.width(), page.height(), 0, 0)
        assert scroll.horizontalScrollBar().value() > 0
        assert scroll.verticalScrollBar().value() > 0
        tabs.setCurrentWidget(other)
        assert tabs.currentWidget() is other
        tabs.removeTab(0)
        assert tabs.indexOf(page) == -1
        tabs.insertTab(0, page, "Wide again")
        assert tabs.widget(0) is page and tabs.count() == 2
        assert len(tabs.findChildren(type(scroll))) == 2
    finally:
        tabs.close()
        tabs.deleteLater()


def test_theme_font_navigation_visibility_and_width_persist(window_factory, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMenu

    build, settings = window_factory
    first = build()
    first.set_theme("light")
    size_action = next(action for menu in first.findChildren(QMenu) for action in menu.actions()
                       if action.isCheckable() and action.data() == 16)
    size_action.trigger()
    first.resizeDocks([first._navigation_dock], [310], Qt.Orientation.Horizontal)
    qapp.processEvents()
    width = first._navigation_dock.width()
    assert first._sidebar_action.isEnabled()
    first._sidebar_action.trigger()
    assert first._navigation_dock.isHidden()
    first.close()
    assert str(settings.value("workspace/navigation_visible")).lower() == "false"
    second = build()
    assert second._theme_name == "light"
    assert second._user_font_pt == 16
    assert second._navigation_dock.isHidden()
    # Closing a window while the restored panel stays hidden must not replace
    # its saved width with the dock's not-yet-laid-out default geometry.
    second.close()
    third = build()
    third._sidebar_action.trigger()
    qapp.processEvents()
    assert abs(third._navigation_dock.width() - width) <= 2
    assert settings.fileName().endswith("workspace.ini")


def test_invalid_preferences_fall_back_to_defaults(window_factory):
    build, settings = window_factory
    settings.setValue("workspace/theme", "missing")
    settings.setValue("workspace/font_pt", "broken")
    settings.setValue("workspace/navigation_width", -1)
    settings.setValue("workspace/navigation_visible", "broken")
    window = build()
    assert window._theme_name == "dark"
    assert window._user_font_pt == 0
    assert not window._navigation_dock.isHidden()
    assert window._navigation_dock.width() >= 200


def test_default_settings_follow_the_current_home(qapp, monkeypatch, tmp_path):
    from pathlib import Path
    from je_auto_control.gui.workspace_settings import default_settings

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    settings = default_settings()
    settings.setValue("workspace/theme", "light")
    settings.sync()
    assert Path(settings.fileName()) == tmp_path / ".je_auto_control" / "gui.ini"


def test_close_button_closes_its_page_after_tab_insertion(qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QTabBar, QWidget
    from je_auto_control.gui.workspace import ScrollableTabs

    tabs = ScrollableTabs()
    page = QWidget()
    tabs.addTab(page, "First")
    tabs.insertTab(0, QWidget(), "Inserted")
    requested = []
    tabs.tabCloseRequested.connect(requested.append)
    side = QTabBar.ButtonPosition.RightSide
    button = tabs.tabBar().tabButton(1, side)
    try:
        assert button.focusPolicy() == Qt.FocusPolicy.StrongFocus
        button.click()
        assert requested == [1]
    finally:
        tabs.deleteLater()
