"""GUI smoke tests for the window-level Actions menu tab hooks.

The probe runs in a subprocess: building the full tab set creates Qt
widgets and native helper threads whose teardown can abort the host
interpreter long after this module finishes (seen in CI as
``Fatal Python error: Aborted`` inside a later, unrelated test file).
Quarantining the Qt lifetime in a child process keeps the rest of the
headless suite deterministic.
"""
import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

_PROBE = r"""
import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from je_auto_control.gui.main_widget import AutoControlGUIWidget

# Interactive panels that intentionally keep their own in-tab layouts
# instead of exposing commands through the Actions menu.
MENU_EXEMPT_TABS = {"script_builder", "remote_desktop"}

app = QApplication.instance() or QApplication([])
widget = AutoControlGUIWidget()


def entry_actions(entry):
    if entry.actions:
        return list(entry.actions)
    provider = getattr(entry.widget, "menu_actions", None)
    return list(provider()) if callable(provider) else []


report = {
    "missing_actions": [],
    "bad_pairs": [],
    "record_menu_matches": False,
    "variables_menu_matches": False,
    "variables_has_actions": False,
    # Reported from here because this probe already pays for the Qt startup
    # the count needs; a second subprocess just to count tabs is not worth it.
    "tab_count": len(widget._tab_entries),
}

for entry in widget._tab_entries:
    actions = entry_actions(entry)
    if entry.key not in MENU_EXEMPT_TABS and not actions:
        report["missing_actions"].append(entry.key)
    for action in actions:
        if (
            not isinstance(action, (tuple, list)) or len(action) != 2
            or not isinstance(action[0], str) or not action[0]
            or not callable(action[1])
        ):
            report["bad_pairs"].append(entry.key)

record_entry = next(e for e in widget._tab_entries if e.key == "record")
widget.tabs.setCurrentWidget(record_entry.widget)
report["record_menu_matches"] = (
    widget.current_tab_menu_actions() == list(record_entry.actions)
)

widget.show_tab("variables")
variables_entry = next(e for e in widget._tab_entries if e.key == "variables")
widget.tabs.setCurrentWidget(variables_entry.widget)
menu_actions = widget.current_tab_menu_actions()
report["variables_menu_matches"] = (
    menu_actions == variables_entry.widget.menu_actions()
)
report["variables_has_actions"] = bool(menu_actions)

sys.stdout.write(json.dumps(report))
sys.stdout.flush()
# Skip Qt/native-thread teardown entirely: some tabs start helper threads
# at construction and interpreter shutdown can abort. The report is
# already on stdout, so a hard exit is the safe end for this probe.
os._exit(0)
"""


@pytest.fixture(scope="module")
def report():
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    # subprocess spawned with [sys.executable, ...] — known interpreter,
    # fixed argv list, no shell=True, no user input.
    completed = subprocess.run(  # nosec B603  # nosemgrep
        [sys.executable, "-c", _PROBE],
        capture_output=True, text=True, check=False, timeout=180, env=env,
    )
    if completed.returncode != 0:
        pytest.fail(
            "Actions-menu probe subprocess failed "
            f"(exit {completed.returncode}):\n{completed.stderr}"
        )
    return json.loads(completed.stdout)


def test_every_tab_exposes_menu_actions(report):
    assert report["missing_actions"] == []


def test_menu_actions_are_key_handler_pairs(report):
    assert report["bad_pairs"] == []


def test_current_tab_menu_actions_follows_active_tab(report):
    assert report["record_menu_matches"]


def test_hook_tab_actions_reach_the_menu(report):
    assert report["variables_menu_matches"]
    assert report["variables_has_actions"], (
        "hook-based tab should surface its actions"
    )


# The other documented counts are guarded by test_doc_counts.py. The tab count
# lives here instead because counting tabs means constructing the widget, which
# means Qt — and this module already runs it in a subprocess for that reason.
TAB_CITATIONS = (
    ("README.md", r"\((\d+) tabs\)"),
    ("README/README_zh-CN.md", r"（(\d+) 个标签页）"),
    ("README/README_zh-TW.md", r"（(\d+) 個分頁）"),
)


@pytest.mark.parametrize("doc,pattern", TAB_CITATIONS)
def test_documented_tab_count_matches_the_widget(report, doc, pattern):
    root = pathlib.Path(__file__).resolve().parents[3]
    text = (root / doc).read_text(encoding="utf-8")
    found = re.findall(pattern, text)
    assert found, (
        f"{doc}: no longer states the tab count in the expected form "
        f"({pattern!r}). If the wording changed on purpose, update this "
        f"pattern; the count itself must stay in the document."
    )
    for quoted in found:
        assert int(quoted) == report["tab_count"], (
            f"{doc} says {quoted} GUI tabs, the widget builds "
            f"{report['tab_count']}. Update all three READMEs."
        )
