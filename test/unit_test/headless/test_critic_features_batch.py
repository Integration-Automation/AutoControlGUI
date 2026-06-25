"""Headless tests for per-step critic features + rule-based scorer (pure stdlib)."""
import je_auto_control as ac
from je_auto_control.utils.critic_features import (
    build_critic_record, score_step_rule_based, to_judge_prompt,
)


def _el(x, y, name="", role="button"):
    return {"x": x, "y": y, "width": 40, "height": 20, "role": role, "name": name}


def test_record_captures_effect_and_delta():
    before = [_el(0, 0, "A")]
    after = [_el(0, 0, "A"), _el(40, 40, "Popup", role="dialog")]
    record = build_critic_record({"x": 50, "y": 50}, before, after)
    assert record["effect"]["effect"] == "changed_near_target"
    assert record["delta_counts"]["added"] == 1


def test_score_good_step():
    before = [_el(0, 0, "A")]
    after = [_el(0, 0, "A"), _el(40, 40, "Popup", role="dialog")]
    score = score_step_rule_based(build_critic_record({"x": 50, "y": 50},
                                                      before, after))
    assert score["outcome"] is True
    assert abs(score["process_score"] - 1.0) < 1e-9


def test_score_no_op_fails():
    frame = [_el(0, 0, "A")]
    score = score_step_rule_based(build_critic_record({"x": 9, "y": 9},
                                                      frame, list(frame)))
    assert score["outcome"] is False
    assert abs(score["process_score"]) < 1e-9


def test_postcondition_failure_lowers_outcome():
    before = [_el(0, 0, "A")]
    after = [_el(0, 0, "A"), _el(40, 40, "Popup", role="dialog")]
    spec = {"appears": {"role": "menu"}}          # a menu that never appears
    record = build_critic_record({"x": 50, "y": 50}, before, after,
                                 postcondition=spec)
    score = score_step_rule_based(record)
    assert score["outcome"] is False              # effect ok but postcondition failed
    assert record["postcondition"]["ok"] is False


def test_to_judge_prompt_mentions_effect():
    before = [_el(0, 0, "A")]
    after = [_el(0, 0, "A"), _el(40, 40, "P", role="dialog")]
    text = to_judge_prompt(build_critic_record({"x": 50, "y": 50}, before, after))
    assert "Effect:" in text and "changed_near_target" in text


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_build_critic_record", "AC_score_step"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_build_critic_record", "ac_score_step"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_build_critic_record", "AC_score_step"} <= specs


def test_facade_exports():
    for name in ("build_critic_record", "score_step_rule_based", "to_judge_prompt"):
        assert hasattr(ac, name) and name in ac.__all__
