"""Headless tests for the repair-tactic policy / loop (pure stdlib, injected seams)."""
import je_auto_control as ac
from je_auto_control.utils.step_repair import (
    RepairPolicy, next_tactic, plan_repair, run_with_repair,
)


def test_plan_repair_orders_tactics_for_no_op():
    plan = plan_repair("no_op", policy=RepairPolicy(max_attempts=3))
    assert plan == ["wait_retry", "relocate", "nudge"]


def test_plan_repair_escalates_on_changed_elsewhere():
    assert plan_repair("changed_elsewhere") == ["escalate"]


def test_plan_repair_accepts_effect_verdict_dict():
    assert plan_repair({"effect": "changed_elsewhere"}) == ["escalate"]


def test_next_tactic_skips_used():
    assert next_tactic("no_op", ["wait_retry"]) == "relocate"
    assert next_tactic("changed_elsewhere", ["escalate"]) is None


def test_run_with_repair_recovers_after_a_tactic():
    calls = {"act": 0}
    # verify succeeds only on the 3rd act (i.e. after two repair tactics)
    def act():
        calls["act"] += 1
    def verify():
        return calls["act"] >= 3
    used = []
    outcome = run_with_repair(act, verify, apply_tactic=used.append)
    assert outcome.ok is True
    assert outcome.attempts == 3
    assert used == ["wait_retry", "relocate"]


def test_run_with_repair_exhausts_and_fails():
    outcome = run_with_repair(lambda: None, lambda: False,
                              policy=RepairPolicy(max_attempts=2))
    assert outcome.ok is False
    assert outcome.attempts == 3 and len(outcome.tactics_used) == 2


def test_run_with_repair_ok_first_try():
    outcome = run_with_repair(lambda: None, lambda: True)
    assert outcome.ok is True and outcome.attempts == 1
    assert outcome.tactics_used == []


# --- wiring ---------------------------------------------------------------

def test_wiring():
    assert "AC_plan_repair" in set(ac.executor.known_commands())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_plan_repair" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_plan_repair" in specs


def test_facade_exports():
    for name in ("RepairPolicy", "RepairOutcome", "plan_repair", "next_tactic",
                 "run_with_repair"):
        assert hasattr(ac, name) and name in ac.__all__
