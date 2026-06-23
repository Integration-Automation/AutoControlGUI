"""Headless tests for declarative action postconditions (pure stdlib)."""
import je_auto_control as ac
from je_auto_control.utils.postcondition import (
    check_postcondition, compile_postcondition,
)


def _el(name, role="button", enabled=True):
    return {"role": role, "name": name, "enabled": enabled, "x": 0, "y": 0,
            "width": 10, "height": 10}


def test_new_dialog_appears_against_before():
    before = [_el("Save", role="button")]
    after = [_el("Save"), _el("Saved", role="dialog")]
    report = check_postcondition(after, {"appears": {"role": "dialog"}},
                                 before=before)
    assert report.ok is True


def test_appears_fails_if_already_present():
    before = [_el("Saved", role="dialog")]
    after = [_el("Saved", role="dialog")]
    report = check_postcondition(after, {"appears": {"role": "dialog"}},
                                 before=before)
    assert report.ok is False and "appears" in report.failed


def test_disabled_and_text_present_clauses():
    after = [_el("Submit", enabled=False), _el("Saved", role="dialog")]
    report = check_postcondition(after, {"disabled": {"name": "Submit"},
                                         "text_present": "Saved"})
    assert report.ok is True
    assert all(c["ok"] for c in report.clauses)


def test_count_clause():
    after = [_el(f"r{i}", role="row") for i in range(5)]
    assert check_postcondition(after, {"count": {"match": {"role": "row"},
                                                 "equals": 5}}).ok is True
    assert check_postcondition(after, {"count": {"match": {"role": "row"},
                                                 "min": 6}}).ok is False


def test_disappears_needs_before_and_works():
    before = [_el("Spinner", role="img")]
    after = [_el("Done", role="dialog")]
    assert check_postcondition(after, {"disappears": {"role": "img"}},
                               before=before).ok is True
    # without a before frame, disappears cannot be judged → fails
    assert check_postcondition(after, {"disappears": {"role": "img"}}).ok is False


def test_unknown_clause_fails_cleanly():
    report = check_postcondition([_el("X")], {"levitates": {"name": "X"}})
    assert report.ok is False and "levitates" in report.failed


def test_compile_postcondition_predicate():
    predicate = compile_postcondition({"text_present": "OK"})
    assert predicate([_el("OK dialog", role="dialog")]) is True
    assert predicate([_el("Nope")]) is False


# --- wiring ---------------------------------------------------------------

def test_wiring():
    assert "AC_check_postcondition" in set(ac.executor.known_commands())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_check_postcondition" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_check_postcondition" in specs


def test_facade_exports():
    for name in ("check_postcondition", "compile_postcondition",
                 "PostconditionReport"):
        assert hasattr(ac, name) and name in ac.__all__
