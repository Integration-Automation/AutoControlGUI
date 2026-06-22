"""Headless tests for flow checkpoint & resume (durable execution) and the
py.typed marker. Pure stdlib; no Qt imports."""
import je_auto_control as ac
from je_auto_control.utils.checkpoint import (
    CheckpointStore, run_resumable)


def _program():
    return [["AC_set_var", {"name": "a", "value": 1}],
            ["AC_set_var", {"name": "b", "value": 2}],
            ["AC_inc_var", {"name": "a", "by": 10}]]


def test_store_save_load_clear(tmp_path):
    store = CheckpointStore(str(tmp_path / "c.db"))
    assert store.load("r1") is None
    store.save("r1", 2, {"x": 5})
    cp = store.load("r1")
    assert cp.step_index == 2 and cp.variables == {"x": 5}
    store.save("r1", 3, {"x": 6})              # upsert
    assert store.load("r1").step_index == 3
    assert store.clear("r1") is True
    assert store.clear("r1") is False
    assert store.load("r1") is None


def test_run_resumable_full_run(tmp_path):
    store = CheckpointStore(str(tmp_path / "c.db"))
    result = run_resumable(_program(), run_id="run", store=store)
    assert result["completed"] is True
    assert result["resumed_from"] == 0 and result["total"] == 3
    assert store.load("run") is None           # cleared on completion


def test_run_resumable_resumes_from_checkpoint(tmp_path):
    store = CheckpointStore(str(tmp_path / "c.db"))
    # Simulate a crash after step 0: step 1 is next, var 'a' already set.
    store.save("run", 1, {"a": 1})
    result = run_resumable(_program(), run_id="run", store=store)
    assert result["resumed_from"] == 1
    # only steps 1 and 2 ran; the record reflects two executed actions
    assert sum("execute:" in k for k in result["record"]) == 2


def test_run_resumable_rehydrates_variables(tmp_path):
    store = CheckpointStore(str(tmp_path / "c.db"))
    store.save("run", 2, {"a": 100, "b": 2})   # resume at the inc step
    actions = _program()
    executor = ac.executor.__class__()         # fresh isolated executor
    run_resumable(actions, run_id="run", store=store, executor=executor)
    assert executor.variables.get_value("a") == 110   # 100 + 10


# --- py.typed marker ------------------------------------------------------

def test_py_typed_marker_present():
    import os
    import je_auto_control
    pkg_dir = os.path.dirname(je_auto_control.__file__)
    assert os.path.isfile(os.path.join(pkg_dir, "py.typed"))


# --- wiring ---------------------------------------------------------------

def test_executor_wiring(tmp_path):
    db = str(tmp_path / "e.db")
    rec = ac.execute_action([["AC_run_resumable", {
        "actions": [["AC_set_var", {"name": "z", "value": 9}]],
        "run_id": "w", "db": db}]])
    assert any("'completed': True" in str(v) for v in rec.values())
    status = ac.execute_action([["AC_checkpoint_status",
                                 {"run_id": "w", "db": db}]])
    assert any("None" in str(v) for v in status.values())   # cleared
    known = ac.executor.known_commands()
    assert {"AC_run_resumable", "AC_checkpoint_status",
            "AC_checkpoint_clear"} <= known


def test_mcp_and_builder_wiring():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_run_resumable", "ac_checkpoint_status",
            "ac_checkpoint_clear"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_run_resumable", "AC_checkpoint_status",
            "AC_checkpoint_clear"} <= cmds


def test_facade_exports():
    for attr in ("Checkpoint", "CheckpointStore", "run_resumable"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
