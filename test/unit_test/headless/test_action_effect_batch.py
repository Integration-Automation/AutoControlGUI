"""Headless tests for action-effect classification (pure stdlib)."""
import je_auto_control as ac
from je_auto_control.utils.action_effect import (
    classify_effect, effect_near_point, is_no_op,
)


def _el(x, y, name="", role="button"):
    return {"x": x, "y": y, "width": 40, "height": 20, "role": role, "name": name}


def test_no_op_when_nothing_changes():
    frame = [_el(0, 0, "A"), _el(0, 40, "B")]
    verdict = classify_effect(frame, list(frame), {"x": 10, "y": 10})
    assert verdict.effect == "no_op"
    assert is_no_op(frame, list(frame)) is True


def test_changed_near_target():
    before = [_el(0, 0, "A")]
    after = [_el(0, 0, "A"), _el(40, 40, "Popup")]   # new element near (50,50)
    verdict = classify_effect(before, after, {"x": 50, "y": 50}, radius=64)
    assert verdict.effect == "changed_near_target"
    assert verdict.changed_near_target is True
    assert verdict.changed_count == 1


def test_changed_elsewhere():
    before = [_el(0, 0, "A")]
    after = [_el(0, 0, "A"), _el(500, 500, "FarDialog")]
    verdict = classify_effect(before, after, {"x": 10, "y": 10}, radius=64)
    assert verdict.effect == "changed_elsewhere"
    assert verdict.changed_near_target is False


def test_changed_without_target_point():
    before = [_el(0, 0, "A")]
    after = [_el(0, 0, "A"), _el(80, 80, "New")]
    verdict = classify_effect(before, after, {"type": "key", "keys": "enter"})
    assert verdict.effect == "changed"


def test_effect_near_point_helper():
    before = [_el(0, 0, "A")]
    after = [_el(0, 0, "A"), _el(40, 40, "X")]
    assert effect_near_point(before, after, [50, 50], radius=64) is True
    assert effect_near_point(before, after, [500, 500], radius=64) is False


def test_rename_counts_as_change():
    before = [_el(0, 0, "Submit")]
    after = [_el(0, 0, "Submitting")]
    assert is_no_op(before, after) is False


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_classify_effect", "AC_effect_near_point"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_classify_effect", "ac_effect_near_point"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_classify_effect", "AC_effect_near_point"} <= specs


def test_facade_exports():
    for name in ("classify_effect", "effect_near_point", "is_no_op",
                 "EffectVerdict"):
        assert hasattr(ac, name) and name in ac.__all__
