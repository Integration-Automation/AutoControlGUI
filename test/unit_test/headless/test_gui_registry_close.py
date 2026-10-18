"""Explicit registry close releases feature resources without changing hide semantics."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    widgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    return widgets.QApplication.instance() or widgets.QApplication([])


def _flush(qapp):
    from PySide6.QtCore import QEvent
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


def test_registry_open_is_lazy_and_close_recreates_the_same_key(qapp):
    from PySide6.QtWidgets import QWidget
    from je_auto_control.gui.tab_registry import TabEntry, TabRegistry

    built, closed = [], []

    def factory():
        page = QWidget()
        page.tab_key = "feature"
        built.append(page)
        return page

    entry = TabEntry("feature", "feature", factory)
    registry = TabRegistry([entry], on_close=closed.append)
    registry.close("feature")
    assert not entry.built and built == []
    first = registry.open("feature")
    assert registry.open("feature") is first
    registry.close("feature")
    assert not entry.built and closed == [first]
    _flush(qapp)
    second = registry.open("feature")
    assert second is not first and second.tab_key == first.tab_key
    registry.close("feature")
    _flush(qapp)


def test_registry_respects_a_rejected_close(qapp):
    from PySide6.QtWidgets import QWidget
    from je_auto_control.gui.tab_registry import TabEntry, TabRegistry

    class UnsavedPage(QWidget):
        def closeEvent(self, event):
            event.ignore()

    closed = []
    entry = TabEntry("unsaved", "unsaved", UnsavedPage)
    registry = TabRegistry([entry], on_close=closed.append)
    page = registry.open("unsaved")
    registry.close("unsaved")
    assert entry.built and registry.open("unsaved") is page
    assert closed == []
    page.deleteLater()


@pytest.fixture
def workspace(qapp, monkeypatch):
    from PySide6.QtWidgets import QWidget
    from je_auto_control.gui import main_widget
    monkeypatch.setattr(main_widget, "TAB_SPECS", tuple(
        spec for spec in main_widget.TAB_SPECS if spec.key in {"record", "presence", "live_hud", "remote_desktop"}
    ))
    monkeypatch.setattr(main_widget.AutoControlGUIWidget, "_build_remote_desktop_tab", staticmethod(QWidget))
    widget = main_widget.AutoControlGUIWidget()
    yield widget
    widget.deleteLater()
    _flush(qapp)


def test_close_button_releases_presence_listener_and_reopen_resubscribes(workspace, qapp):
    from je_auto_control.utils.remote_desktop.presence import default_presence_registry
    registry = default_presence_registry()
    baseline = len(registry._listeners)
    workspace.show_tab("presence")
    entry = workspace._find_entry("presence")
    first = entry.widget
    assert len(registry._listeners) == baseline + 1
    workspace._on_tab_close_requested(workspace.tabs.indexOf(first))
    assert not entry.built
    assert not next(row for row in workspace.list_registered_tabs() if row["key"] == "presence")["visible"]
    _flush(qapp)
    assert len(registry._listeners) == baseline
    workspace.show_tab("presence")
    assert entry.widget is not first and len(registry._listeners) == baseline + 1


def test_close_detaches_hud_log_tail(workspace, qapp):
    from je_auto_control.utils.logging.logging_instance import autocontrol_logger
    workspace.show_tab("live_hud")
    entry = workspace._find_entry("live_hud")
    tail = entry.widget._log_tail
    entry.widget._start()
    assert tail in autocontrol_logger.handlers
    workspace.close_tab("live_hud")
    _flush(qapp)
    assert not entry.built and tail not in autocontrol_logger.handlers


def test_hide_still_reuses_a_panel_and_explicit_close_can_release_it(workspace, qapp):
    workspace.show_tab("presence")
    entry = workspace._find_entry("presence")
    page = entry.widget
    workspace.hide_tab("presence")
    assert entry.built
    workspace.show_tab("presence")
    assert entry.widget is page
    workspace.hide_tab("presence")
    workspace.close_tab("presence")
    assert not entry.built
    _flush(qapp)


def test_unknown_key_does_not_build_any_registered_page(workspace):
    from je_auto_control.utils.exception.exceptions import AutoControlException
    before = [entry.built for entry in workspace._tab_entries]
    with pytest.raises(AutoControlException, match="Unknown tab"):
        workspace.tab_registry.open("missing")
    workspace.tab_registry.close("missing")
    assert [entry.built for entry in workspace._tab_entries] == before


@pytest.mark.parametrize("key", ["record", "remote_desktop"])
def test_legacy_form_and_remote_session_owner_are_retained_on_close(workspace, key):
    entry = workspace._find_entry(key)
    first = entry.widget
    workspace.close_tab(key)
    assert entry.built and workspace.tabs.indexOf(first) == -1
    workspace.show_tab(key)
    assert entry.widget is first
