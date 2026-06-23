"""Headless tests for composable/filtered candidate locators. No Qt."""
import je_auto_control as ac
from je_auto_control.utils.locator_chain import Candidates, from_boxes


def _b(x, y, w, h, **extra):
    return dict(x=x, y=y, width=w, height=h, **extra)


def _scene():
    return [_b(10, 10, 40, 20, text="Save"), _b(200, 10, 40, 20, text="Delete"),
            _b(60, 10, 40, 20, text="Delete"), _b(10, 200, 40, 20, text="Cancel")]


def test_within_clips_to_region():
    inside = from_boxes(_scene()).within((0, 0, 300, 100))
    assert len(inside) == 3                       # the y=200 Cancel is excluded
    assert "Cancel" not in [b["text"] for b in inside]


def test_filter_has_text_case_insensitive():
    deletes = from_boxes(_scene()).filter(has_text="delete")
    assert len(deletes) == 2 and all(b["text"] == "Delete" for b in deletes)


def test_chained_within_filter_nth():
    second = (from_boxes(_scene()).within((0, 0, 300, 100))
              .filter(has_text="Delete").sort_reading().nth(1))
    assert second.center() == [220, 20]           # the right-hand Delete


def test_first_last_and_empty_nth():
    chain = from_boxes(_scene()).sort_reading()
    assert chain.first().center() == [30, 20]     # Save (leftmost top row)
    assert chain.last().center() == [30, 210]     # Cancel (bottom row)
    assert from_boxes(_scene()).nth(99).center() is None


def test_filter_near_and_area_and_predicate():
    assert len(from_boxes(_scene()).filter(near=(30, 20, 30))) == 1
    assert len(from_boxes(_scene()).filter(min_area=10000)) == 0
    cancels = from_boxes(_scene()).filter(predicate=lambda b: b["text"][0] == "C")
    assert len(cancels) == 1


def test_immutable_chaining():
    base = from_boxes(_scene())
    assert isinstance(base, Candidates)
    base.filter(has_text="Save")                  # does not mutate base
    assert len(base) == 4


# --- wiring ---------------------------------------------------------------

def test_wiring():
    assert "AC_locate_chain" in set(ac.executor.known_commands())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_locate_chain" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_locate_chain" in specs


def test_executor_applies_op_chain():
    from je_auto_control.utils.executor.action_executor import _locate_chain
    result = _locate_chain(_scene(), ops=[
        {"op": "within", "region": [0, 0, 300, 100]},
        {"op": "filter", "has_text": "Delete"},
        {"op": "reading"},
        {"op": "nth", "index": 0}])
    assert result["count"] == 1 and result["center"] == [80, 20]


def test_facade_exports():
    for attr in ("Candidates", "from_boxes"):
        assert hasattr(ac, attr) and attr in ac.__all__
