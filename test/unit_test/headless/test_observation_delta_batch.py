"""Headless tests for the token-budgeted observation delta (pure stdlib)."""
import je_auto_control as ac
from je_auto_control.utils.observation_delta import (
    delta_index, delta_observation, summarize_delta,
)


def _el(x, y, role="button", name="", **extra):
    return dict(x=x, y=y, width=40, height=20, role=role, name=name, **extra)


def test_added_removed_changed_stable_classification():
    prev = [_el(0, 0, name="A"), _el(0, 40, name="B"), _el(0, 80, name="Spin")]
    # A unchanged; B renamed; Spin gone; C new
    curr = [_el(0, 0, name="A"), _el(0, 40, name="B2"), _el(0, 120, name="C")]
    delta = delta_index(prev, curr)
    assert [e["name"] for e in delta["added"]] == ["C"]
    assert [e["name"] for e in delta["removed"]] == ["Spin"]
    assert delta["changed"][0]["after"]["name"] == "B2"
    assert "name" in delta["changed"][0]["fields"]
    assert [e["name"] for e in delta["stable"]] == ["A"]


def test_moved_is_a_change():
    prev = [_el(0, 0, name="X")]
    curr = [_el(50, 0, name="X")]  # same identity (overlap), moved > threshold
    delta = delta_index(prev, curr, iou_threshold=0.0)
    assert delta["changed"] and "moved" in delta["changed"][0]["fields"]


def test_summarize_renders_markers_and_drops_stable():
    prev = [_el(0, 0, name="A"), _el(0, 40, name="B")]
    curr = [_el(0, 0, name="A"), _el(0, 40, name="B2"), _el(0, 80, name="C")]
    text = summarize_delta(delta_index(prev, curr))
    assert "+ " in text and "~ " in text  # C added, B changed
    assert '"A"' not in text              # stable A is omitted


def test_max_lines_budget_truncates():
    prev = []
    curr = [_el(0, i * 25, name=f"n{i}") for i in range(10)]
    text = summarize_delta(delta_index(prev, curr), max_lines=3)
    assert text.count("\n") == 3  # 3 lines + the "(+N more)" line
    assert "more)" in text


def test_delta_observation_end_to_end():
    prev = [_el(0, 0, name="Old")]
    curr = [_el(0, 0, name="Old"), _el(0, 50, name="New")]
    text = delta_observation(prev, curr, interactive_only=False)
    assert '+ [' in text and '"New"' in text


# --- wiring ---------------------------------------------------------------

def test_wiring():
    assert "AC_delta_observation" in set(ac.executor.known_commands())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_delta_observation" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_delta_observation" in specs


def test_facade_exports():
    for name in ("delta_index", "delta_observation", "summarize_delta"):
        assert hasattr(ac, name) and name in ac.__all__
