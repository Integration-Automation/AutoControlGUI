"""Headless tests for element_proposal (pure tag_kinds + cv2 pipeline)."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.element_proposal import propose_elements, tag_kinds


# --- pure tag_kinds -------------------------------------------------------

def test_tag_kinds_labels_by_source():
    fused = [
        {"x": 0, "y": 0, "width": 30, "height": 12, "source": "ocr",
         "index": 0},
        {"x": 0, "y": 20, "width": 16, "height": 16, "source": "icon",
         "index": 1},
    ]
    tagged = tag_kinds(fused)
    assert tagged[0] == {"box": [0, 0, 30, 12], "kind": "text", "index": 0}
    assert tagged[1] == {"box": [0, 20, 16, 16], "kind": "widget", "index": 1}


def test_tag_kinds_unknown_source_is_widget():
    tagged = tag_kinds([{"x": 1, "y": 2, "width": 3, "height": 4}])
    assert tagged[0]["kind"] == "widget"
    assert tagged[0]["box"] == [1, 2, 3, 4]


def test_tag_kinds_empty():
    assert tag_kinds([]) == []


# --- cv2 propose_elements (per-function importorskip) ---------------------

def test_propose_elements_finds_widgets():
    np = pytest.importorskip("numpy")
    cv2 = pytest.importorskip("cv2")
    canvas = np.full((200, 240), 245, dtype="uint8")
    # three distinct outlined "widgets"
    cv2.rectangle(canvas, (20, 20), (90, 60), 0, 2)
    cv2.rectangle(canvas, (130, 30), (210, 70), 0, 2)
    cv2.rectangle(canvas, (40, 110), (200, 160), 0, 2)
    elements = propose_elements(canvas, min_area=120)
    assert len(elements) >= 2
    # every element is well-formed and in reading order
    for position, element in enumerate(elements):
        assert set(element) == {"box", "kind", "index"}
        assert element["index"] == position
        assert element["kind"] in ("text", "widget")
        assert len(element["box"]) == 4
    # nothing spans the whole frame
    assert all(not (e["box"][2] >= 228 and e["box"][3] >= 190)
               for e in elements)


def test_propose_elements_blank_screen_is_empty_or_small():
    np = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    blank = np.full((120, 120), 255, dtype="uint8")
    assert propose_elements(blank, min_area=200) == []


# --- wiring (cv2-free) ----------------------------------------------------

def test_executor_pure_tag_path():
    from je_auto_control.utils.executor.action_executor import _tag_kinds
    out = _tag_kinds('[{"x":0,"y":0,"width":10,"height":10,"source":"icon"}]')
    assert out["elements"][0]["kind"] == "widget"


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_propose_elements", "AC_tag_kinds"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_propose_elements", "ac_tag_kinds"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_propose_elements", "AC_tag_kinds"} <= specs


def test_facade_exports():
    for name in ("propose_elements", "tag_kinds"):
        assert hasattr(ac, name) and name in ac.__all__
