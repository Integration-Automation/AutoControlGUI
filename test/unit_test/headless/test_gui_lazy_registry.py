"""The tab registry: every tab is listed, and none is built before it is opened.

The table and ``TabEntry`` are checked without Qt. What the real widget
builds at start-up is measured in a child process: in this one, other test
modules have long since imported most tab modules.
"""
import importlib.util
import json
import os
import pathlib
import subprocess  # nosec B404  # reason: runs this file's own probe with a fixed argv
import sys

import pytest

from je_auto_control.gui.tab_registry import TAB_SPECS, TabEntry, lazy_factory

ROOT = pathlib.Path(__file__).resolve().parents[3]
# Built by the main widget itself: its mixin tabs, and Remote Desktop's placeholder fallback.
OWN_TABS = {"auto_click", "screenshot", "image_detect", "record", "script", "remote_desktop", "report"}
OPEN_AT_START = ["record", "script_builder", "remote_desktop"]


def test_keys_are_unique_and_the_start_tabs_are_the_three_documented():
    keys = [spec.key for spec in TAB_SPECS]
    assert len(keys) == len(set(keys))
    assert [spec.key for spec in TAB_SPECS if spec.default_visible] == OPEN_AT_START
    assert {spec.key for spec in TAB_SPECS if not spec.module} == OWN_TABS


def test_importing_the_registry_loads_no_qt():
    probe = ("import sys; import je_auto_control.gui.tab_registry; "
             "print(any(name.startswith('PySide6') for name in sys.modules))")
    done = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,  # nosec B603  # nosemgrep  # reason: fixed argv, no shell
                          timeout=120, cwd=str(ROOT), check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.strip() == "False"


@pytest.mark.parametrize("spec", [spec for spec in TAB_SPECS if spec.module], ids=lambda spec: spec.key)
def test_every_lazy_tab_names_a_class_that_exists(spec):
    """Read, not imported: a typo here would otherwise surface when a user opens the tab."""
    found = importlib.util.find_spec(spec.module)
    assert found is not None, spec.module
    assert found.origin, spec.module
    source = pathlib.Path(found.origin).read_text(encoding="utf-8")
    assert (f"class {spec.class_name}(" in source or f"import {spec.class_name}" in source
            or f"{spec.class_name}," in source or f'"{spec.class_name}"' in source), (spec.module, spec.class_name)


def test_an_entry_builds_its_widget_once_and_only_when_asked():
    built, adopted = [], []

    def factory():
        built.append(object())
        return built[-1]

    entry = TabEntry("k", "tab_k", factory, on_build=adopted.append)
    assert not entry.built
    assert built == []
    first = entry.widget
    assert entry.built
    assert entry.widget is first
    assert built == [first]
    assert adopted == [first]


def test_a_lazy_factory_imports_at_call_time():
    factory = lazy_factory("collections", "OrderedDict")
    assert type(factory()).__name__ == "OrderedDict"
    with pytest.raises(ModuleNotFoundError):
        lazy_factory("je_auto_control.gui.no_such_tab", "Missing")()


_PROBE = r"""
import json, os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from je_auto_control.gui.main_widget import AutoControlGUIWidget
from je_auto_control.gui.tab_registry import TAB_SPECS

app = QApplication.instance() or QApplication([])
widget = AutoControlGUIWidget()
entries = {entry.key: entry for entry in widget._tab_entries}
report = {
    "registered": [entry.key for entry in widget._tab_entries],
    "specs": [spec.key for spec in TAB_SPECS],
    "built_at_start": [key for key, entry in entries.items() if entry.built],
    "open_at_start": [row["key"] for row in widget.list_registered_tabs() if row["visible"]],
    "variables_imported_at_start": "je_auto_control.gui.variables_tab" in sys.modules,
    "presence_imported_at_start": "je_auto_control.gui.presence_tab" in sys.modules,
    "script_builder_imported_at_start": "je_auto_control.gui.script_builder" in sys.modules,
    "remote_desktop_imported_at_start": "je_auto_control.gui.remote_desktop_tab" in sys.modules,
    "current_at_start": widget.current_tab_key(),
}
widget.list_registered_tabs()
widget.retranslate()
widget.sync_engine_tabs()
widget.hide_tab("variables")
report["built_after_listing"] = [key for key, entry in entries.items() if entry.built]

changes = []
widget.tabs_changed.connect(lambda: changes.append(1))
widget.show_tab("variables")
first = entries["variables"].widget
report["variables_imported_after_open"] = "je_auto_control.gui.variables_tab" in sys.modules
report["current_after_open"] = widget.current_tab_key()
widget.hide_tab("variables")
report["hidden_is_owned"] = widget.isAncestorOf(first) and widget.tabs.indexOf(first) == -1
report["activated"] = widget.activate_tab("variables")
report["same_widget_on_reopen"] = entries["variables"].widget is first
report["tab_order"] = [row["key"] for row in widget.list_registered_tabs() if row["visible"]]
widget.activate_tab("record")
report["current_after_activate"] = widget.current_tab_key()
report["changes"] = len(changes)
report["unknown"] = widget.activate_tab("no_such_tab")

# A start tab that has never been in front: closed and reopened without being built, built when selected.
widget.hide_tab("script_builder")
still_open = [r["key"] for r in widget.list_registered_tabs() if r["visible"]]
report["closed_unbuilt"] = not entries["script_builder"].built and "script_builder" not in still_open
widget.show_tab("script_builder")
builder = entries["script_builder"].widget
report["builder_selected"] = [widget.current_tab_key(), widget.tabs.indexOf(builder),
                              widget.tabs.currentWidget() is builder]
widget.tabs.setCurrentIndex(widget.tabs.count() - 1)
report["remote_built_on_select"] = [entries["remote_desktop"].built, widget.current_tab_key()]
report["scrolls"] = {key: widget.tabs.is_scrollable(widget.tabs.indexOf(entries[key].widget))
                     for key in ("record", "script_builder", "remote_desktop")}
sys.stdout.write(json.dumps(report))
sys.stdout.flush()
os._exit(0)
"""


@pytest.fixture(scope="module")
def report():
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    done = subprocess.run([sys.executable, "-c", _PROBE], capture_output=True, text=True,  # nosec B603  # nosemgrep  # reason: fixed argv, no shell
                          timeout=180, env=env, cwd=str(ROOT), check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


def test_every_spec_is_registered_in_order(report):
    assert report["registered"] == report["specs"]


def test_only_the_start_tabs_and_the_widgets_own_forms_are_built(report):
    # Record is in front; Script Builder and Remote Desktop have a tab but wait for the first click.
    assert set(report["built_at_start"]) == OWN_TABS - {"remote_desktop"}
    assert report["open_at_start"] == OPEN_AT_START
    assert report["current_at_start"] == "record"
    assert not report["variables_imported_at_start"]
    assert not report["presence_imported_at_start"]
    assert not report["script_builder_imported_at_start"]
    assert not report["remote_desktop_imported_at_start"]


def test_a_start_tab_is_built_when_it_first_comes_to_the_front(report):
    assert report["closed_unbuilt"]
    assert report["builder_selected"] == ["script_builder", 1, True]
    assert report["remote_built_on_select"] == [True, "remote_desktop"]
    # Remote Desktop scrolls itself; the other pages scroll in their tab.
    assert report["scrolls"] == {"record": True, "script_builder": True, "remote_desktop": False}


def test_listing_translating_and_hiding_build_nothing(report):
    assert report["built_after_listing"] == report["built_at_start"]


def test_opening_builds_the_tab_and_reopening_reuses_it(report):
    assert report["variables_imported_after_open"]
    assert report["current_after_open"] == "variables"
    assert report["hidden_is_owned"]
    assert report["activated"]
    assert report["same_widget_on_reopen"]
    # Registration order, not opening order: Variables sits between Script Builder and Remote Desktop.
    assert report["tab_order"] == ["record", "script_builder", "variables", "remote_desktop"]


def test_activating_an_open_tab_only_selects_it(report):
    assert report["current_after_activate"] == "record"
    assert report["changes"] == 3          # opened, hidden, opened again
    assert report["unknown"] is False
