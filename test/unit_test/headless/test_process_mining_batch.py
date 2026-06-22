"""Headless tests for task/process mining over an action log. Deterministic,
pure stdlib, no Qt imports."""
import je_auto_control as ac
from je_auto_control.utils.process_mining import (
    directly_follows, find_repeated_sequences, mine_action_log,
    rank_automation_candidates)

# "open, type, save" repeated 3x, plus noise
LOG = (
    [["AC_focus_window", {}], ["AC_type_text", {}], ["AC_hotkey", {}]] * 3
    + [["AC_screenshot", {}]]
)


def test_find_repeated_sequences():
    patterns = find_repeated_sequences(LOG, min_len=3, max_len=3, min_count=3)
    grams = {p.actions for p in patterns}
    assert ("AC_focus_window", "AC_type_text", "AC_hotkey") in grams
    top = next(p for p in patterns
               if p.actions[0] == "AC_focus_window")
    assert top.count == 3


def test_min_count_filters():
    # the screenshot appears once -> never a candidate at min_count=3
    patterns = find_repeated_sequences(LOG, min_len=1, max_len=1, min_count=3)
    singles = {p.actions[0] for p in patterns}
    assert "AC_screenshot" not in singles
    assert "AC_type_text" in singles      # appears 3x


def test_directly_follows_edges():
    edges = directly_follows(LOG)
    assert edges[("AC_focus_window", "AC_type_text")] == 3
    assert edges[("AC_type_text", "AC_hotkey")] == 3


def test_candidates_ranked_by_count_times_length():
    report = mine_action_log(LOG, min_len=2, max_len=3, min_count=3)
    assert report.candidates
    scores = [c.score for c in report.candidates]
    assert scores == sorted(scores, reverse=True)
    # the length-3 pattern (3*3=9) outranks a length-2 pattern (3*2=6)
    assert report.candidates[0].score == 9


def test_accepts_dict_and_pair_shapes():
    mixed = [{"command": "A"}, {"command": "B"}] * 3
    report = mine_action_log(mixed, min_len=2, max_len=2, min_count=3)
    assert report.total_actions == 6
    assert any(c.pattern.actions == ("A", "B") for c in report.candidates)


def test_no_patterns_when_unique():
    report = mine_action_log([["A", {}], ["B", {}], ["C", {}]], min_count=3)
    assert report.patterns == [] and report.candidates == []


def test_rank_is_stable_on_empty():
    assert rank_automation_candidates(
        mine_action_log([], min_count=3)) == []


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([[
        "AC_mine_actions",
        {"actions": LOG, "min_len": 3, "max_len": 3, "min_count": 3},
    ]])
    report = next(v for v in rec.values() if isinstance(v, dict))
    assert report["total_actions"] == 10
    assert report["candidates"][0]["count"] == 3


def test_wiring():
    assert "AC_mine_actions" in ac.executor.known_commands()
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_mine_actions" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert "AC_mine_actions" in cmds


def test_facade_exports():
    for attr in ("mine_action_log", "find_repeated_sequences",
                 "directly_follows", "rank_automation_candidates"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
