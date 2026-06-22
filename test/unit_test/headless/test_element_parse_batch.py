"""Headless tests for element-box fusion / ordering. No Qt."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.element_parse import (
    fuse_elements, iou, merge_boxes, reading_order,
)


def _b(x, y, w, h, **extra):
    return dict(x=x, y=y, width=w, height=h, **extra)


def test_iou_full_half_none():
    assert iou(_b(0, 0, 10, 10), _b(0, 0, 10, 10)) == pytest.approx(1.0)
    assert iou(_b(0, 0, 10, 10), _b(5, 0, 10, 10)) == pytest.approx(1 / 3)
    assert iou(_b(0, 0, 10, 10), _b(100, 100, 10, 10)) == pytest.approx(0.0, abs=1e-9)


def test_merge_drops_near_duplicates():
    merged = merge_boxes([_b(0, 0, 100, 100), _b(1, 1, 100, 100),
                          _b(500, 500, 20, 20)])
    assert len(merged) == 2
    assert merged[0]["width"] == 100             # largest kept first


def test_merge_threshold_controls_strictness():
    boxes = [_b(0, 0, 100, 100), _b(40, 0, 100, 100)]      # ~0.43 IoU
    assert len(merge_boxes(boxes, iou_threshold=0.9)) == 2  # kept as distinct
    assert len(merge_boxes(boxes, iou_threshold=0.3)) == 1  # merged


def test_fuse_prefers_higher_priority_source():
    fused = fuse_elements(
        ocr_boxes=[_b(0, 0, 50, 20, text="OK")],
        a11y_boxes=[_b(1, 0, 50, 20, text="OK", role="button")])
    assert len(fused) == 1
    assert fused[0]["source"] == "a11y" and fused[0]["role"] == "button"


def test_fuse_keeps_disjoint_boxes_from_all_sources():
    fused = fuse_elements(
        ocr_boxes=[_b(0, 0, 20, 20)],
        icon_boxes=[_b(100, 0, 20, 20)],
        a11y_boxes=[_b(200, 0, 20, 20)])
    assert len(fused) == 3
    assert {f["source"] for f in fused} == {"ocr", "icon", "a11y"}


def test_fuse_custom_priority():
    fused = fuse_elements(
        ocr_boxes=[_b(0, 0, 50, 20, text="from-ocr")],
        icon_boxes=[_b(0, 0, 50, 20, text="from-icon")],
        source_priority=("icon", "ocr", "a11y"))
    assert len(fused) == 1 and fused[0]["source"] == "icon"


def test_reading_order_rows_then_columns():
    elements = [_b(100, 0, 20, 20, id="b"), _b(0, 0, 20, 20, id="a"),
                _b(0, 100, 20, 20, id="c")]
    ordered = reading_order(elements)
    assert [(e["id"], e["index"]) for e in ordered] == [("a", 0), ("b", 1),
                                                        ("c", 2)]


def test_reading_order_row_tolerance_bands():
    # tops differ by 5px -> same row when tol >= 5
    elements = [_b(50, 5, 10, 10, id="r"), _b(0, 0, 10, 10, id="l")]
    ordered = reading_order(elements, row_tol=8)
    assert [e["id"] for e in ordered] == ["l", "r"]


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_fuse_elements", "AC_reading_order"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_fuse_elements", "ac_reading_order"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_fuse_elements", "AC_reading_order"} <= specs


def test_facade_exports():
    for attr in ("iou", "merge_boxes", "fuse_elements", "reading_order"):
        assert hasattr(ac, attr) and attr in ac.__all__
