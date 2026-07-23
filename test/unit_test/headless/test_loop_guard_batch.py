"""Headless tests for the mechanical stuck-loop guard. Fully deterministic —
synthetic step sequences, no screenshots. Pure stdlib, no Qt imports."""
import je_auto_control as ac
from je_auto_control.utils.loop_guard import (
    LoopGuard, default_loop_guard, digest_result)


def test_repeat_escalates_ok_warn_critical():
    guard = LoopGuard(warn=3, critical=5)
    levels = [guard.observe("AC_click", {"x": 1}).level for _ in range(6)]
    # 1,2 -> ok; 3,4 -> warn; 5,6 -> critical
    assert levels[:2] == ["ok", "ok"]
    assert levels[2] == "warn" and levels[3] == "warn"
    assert levels[4] == "critical" and levels[5] == "critical"


def test_repeat_pattern_and_count():
    guard = LoopGuard(warn=3, critical=5)
    guard.observe("AC_click", {"x": 1})
    verdict = guard.observe("AC_click", {"x": 1})
    assert verdict.pattern == "repeat" and verdict.count == 2


def test_distinct_args_not_a_repeat():
    guard = LoopGuard()
    guard.observe("AC_click", {"x": 1})
    verdict = guard.observe("AC_click", {"x": 2})   # different args
    assert verdict.pattern is None and verdict.level == "ok"


def test_ping_pong_detected():
    guard = LoopGuard(warn=4, critical=8)
    seq = ["A", "B", "A", "B", "A", "B"]
    verdict = None
    for name in seq:
        verdict = guard.observe(name, None)
    assert verdict.pattern == "ping_pong"
    assert verdict.count >= 4


def test_no_op_when_observation_unchanged():
    guard = LoopGuard(warn=3, critical=5)
    # different actions, but the screen digest never changes
    guard.observe("A", None, result_digest="same")
    guard.observe("B", None, result_digest="same")
    verdict = guard.observe("C", None, result_digest="same")
    assert verdict.pattern == "no_op" and verdict.count == 3


def test_reset_clears_history():
    guard = LoopGuard(warn=2, critical=3)
    guard.observe("A", {"x": 1})
    guard.observe("A", {"x": 1})
    guard.reset()
    verdict = guard.observe("A", {"x": 1})       # only one event after reset
    assert verdict.pattern is None and verdict.level == "ok"


def test_digest_result_stable_and_bytes():
    first_bytes, second_bytes = digest_result(b"abc"), digest_result(b"abc")
    first_dict, second_dict = digest_result({"a": 1}), digest_result({"a": 1})
    assert first_bytes == second_bytes
    assert first_dict == second_dict
    assert first_bytes != digest_result(b"abd")


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    default_loop_guard.reset()
    try:
        ac.execute_action([["AC_loop_guard_observe",
                            {"tool": "AC_click", "args": {"x": 1}}]])
        rec = ac.execute_action([["AC_loop_guard_observe",
                                  {"tool": "AC_click", "args": {"x": 1}}]])
        verdict = next(v for v in rec.values() if isinstance(v, dict))
        assert verdict["pattern"] == "repeat" and verdict["count"] == 2
    finally:
        default_loop_guard.reset()


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_loop_guard_observe", "AC_loop_guard_reset"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_loop_guard_observe", "ac_loop_guard_reset"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_loop_guard_observe", "AC_loop_guard_reset"} <= cmds


def test_facade_exports():
    for attr in ("LoopGuard", "LoopVerdict", "default_loop_guard",
                 "digest_result"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
