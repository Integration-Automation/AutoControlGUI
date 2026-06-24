"""Headless tests for error normalisation + stable failure signatures."""
import je_auto_control as ac
from je_auto_control.utils.failure_signature import (
    failure_signature, group_failures, normalize_error,
)

_RUN_A = r"Timeout locating element at C:\Users\me\app.py line 42 (0x7ffab12c) at 2026-06-24 11:03:21"
_RUN_B = r"Timeout locating element at C:\Users\you\app.py line 99 (0x1234abcd) at 2026-06-25 09:15:00"
_OTHER = "Connection refused to /var/run/db.sock"


def test_normalize_collapses_volatile_parts():
    assert normalize_error(_RUN_A) == (
        "Timeout locating element at <path> line <n> (0x<addr>) at <ts>")


def test_same_failure_same_signature_across_runs():
    assert failure_signature(_RUN_A) == failure_signature(_RUN_B)


def test_different_failure_differs():
    assert failure_signature(_RUN_A) != failure_signature(_OTHER)


def test_signature_length_param():
    assert len(failure_signature(_RUN_A, length=8)) == 8
    assert len(failure_signature(_RUN_A)) == 12


def test_uuid_and_posix_path_normalised():
    msg = "row 00000000-1111-2222-3333-444444444444 at /tmp/x/data.json missing"
    assert normalize_error(msg) == "row <uuid> at <path> missing"


def test_group_failures_counts_and_skips_empty():
    groups = group_failures([_RUN_A, _RUN_B, _OTHER,
                             "Connection refused to /tmp/other.sock", None, ""])
    assert len(groups) == 2
    assert groups[0]["count"] == 2          # most frequent first (tie → 2 each)
    timeout = next(g for g in groups if "Timeout" in g["normalized"])
    assert timeout["count"] == 2
    assert len(timeout["examples"]) == 2    # both raw variants kept (max 3)


# --- wiring ---------------------------------------------------------------

def test_executor_paths():
    from je_auto_control.utils.executor.action_executor import (
        _failure_signature, _group_failures)
    sig = _failure_signature(_RUN_A)
    assert sig["signature"] == failure_signature(_RUN_A)
    assert sig["normalized"].endswith("at <ts>")
    grouped = _group_failures(f'["{_OTHER}", "{_OTHER}"]')
    assert grouped["count"] == 1 and grouped["groups"][0]["count"] == 2


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_failure_signature", "AC_group_failures"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_failure_signature", "ac_group_failures"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_failure_signature", "AC_group_failures"} <= specs


def test_facade_exports():
    for name in ("normalize_error", "failure_signature", "group_failures"):
        assert hasattr(ac, name) and name in ac.__all__
