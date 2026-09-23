"""Executor dispatch defects from the 2026-09-24 audit (fake commands only).

``AC_run_dag`` node actions were placeholder-expanded twice (so a variable's
value containing ``${...}`` was resolved again); a nested ``AC_execute_action``
dropped the enclosing strictness, so ``AC_try`` never caught its failure; a
top-level break overwrote an earlier identical action's record and was named
after the outer action; and a dry run listed repeated actions once.
"""
import pytest

from je_auto_control.utils.executor.action_executor import Executor, executor as global_executor


@pytest.fixture
def ex():
    local = Executor()
    local.event_dict["AC_fake_fail"] = lambda: (_ for _ in ()).throw(ValueError("boom"))
    local.event_dict["AC_fake_ok"] = lambda: "ok"
    return local


def test_dag_node_actions_are_expanded_once():
    seen = []
    global_executor.event_dict["AC_fake_echo"] = lambda v: seen.append(v)
    try:
        global_executor.variables.set("inner", "EXPANDED-TWICE")
        global_executor.variables.set("payload", "${inner}")
        global_executor.execute_action([["AC_run_dag", {"definition": {"nodes": [
            {"id": "a", "actions": [["AC_fake_echo", {"v": "${payload}"}]]}]}}]])
    finally:
        global_executor.event_dict.pop("AC_fake_echo", None)
    assert seen == ["${inner}"]


def test_a_nested_execute_action_failure_reaches_catch(ex):
    ex.execute_action([["AC_try", {
        "body": [["AC_execute_action", {"action_list": [["AC_fake_fail"]]}]],
        "catch": [["AC_set_var", {"name": "c", "value": "caught"}]]}]])
    assert ex.variables.get("c") == "caught"


def test_a_top_level_break_keeps_every_record(ex):
    record = ex.execute_action([
        ["AC_set_var", {"name": "flag", "value": 0}],
        ["AC_define_macro", {"name": "m", "body": [
            ["AC_if_var", {"name": "flag", "op": "eq", "value": 1,
                           "then": [["AC_break"]], "else": [["AC_fake_ok"]]}]]}],
        ["AC_call_macro", {"name": "m"}],
        ["AC_set_var", {"name": "flag", "value": 1}],
        ["AC_call_macro", {"name": "m"}]])
    macro_keys = [key for key in record if "AC_call_macro" in key]
    assert len(macro_keys) == 2
    assert any("AC_break outside a loop" in str(record[key]) for key in macro_keys)


def test_a_dry_run_lists_every_repeat(ex):
    record = ex.execute_action([["AC_fake_ok"]] * 3, dry_run=True)
    assert len(record) == 3
