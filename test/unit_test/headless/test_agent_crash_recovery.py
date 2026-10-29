"""Crash recovery is explicit and uses owned IPC fixtures, never native desktop input."""
import json
from types import SimpleNamespace

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.input_journal import InputJournal
from je_auto_control.utils.agent_runtime.native_recovery import recover_target
from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget
from je_auto_control.utils.agent_runtime.runtime_lock import RuntimeLock
from je_auto_control.utils.rbac.authorization import AuthorizationContext, AuthorizationError, authorization_scope


def test_unfinished_host_ownership_requires_explicit_recovery(tmp_path):
    resource = tmp_path / "input.lock"
    original = InputJournal(resource)
    original.acquire()
    original.update({"keys": [{"keycode": 65, "is_shift": False}], "buttons": []}, "perform")
    replacement = InputJournal(resource)
    with pytest.raises(AgentTaskError, match="explicit crash recovery"):
        replacement.acquire()
    probes = []
    result = replacement.recover("Operator released held inputs and reviewed effects", lambda: probes.append(1), "host")
    assert result["recovered"] and probes == [1]
    assert replacement.read()["held"] == {}
    replacement.acquire()
    replacement.release()


def test_failed_recovery_probe_preserves_original_witness(tmp_path):
    witness = InputJournal(tmp_path / "input.lock")
    witness.acquire()
    before = witness.path.read_bytes()

    def held():
        raise AgentTaskError("release held keys manually")

    with pytest.raises(AgentTaskError, match="manually"):
        witness.recover("Reviewed", held, "host")
    assert witness.path.read_bytes() == before
    with pytest.raises(AgentTaskError, match="review note"):
        witness.recover("", lambda: None, "host")


def test_recovery_never_steals_a_live_resource(tmp_path):
    resource = tmp_path / "input.lock"
    adapter = NativeDesktopTarget(resource_path=resource, recovery_probe=lambda: None)
    owned = RuntimeLock(resource)
    try:
        with pytest.raises(AgentTaskError, match="owns"):
            adapter.recover("Reviewed", actor="host")
    finally:
        owned.close()
    assert adapter.recover("Reviewed", actor="host")["recovered"]


def test_recovery_requires_host_management_authority():
    runtime = SimpleNamespace(_targets={"test": SimpleNamespace(recover=lambda *a, **k: {"recovered": True})})
    with authorization_scope(AuthorizationContext("operator", "operator")):
        with pytest.raises(AuthorizationError, match="manage_hosts"):
            recover_target(runtime, "test", "Reviewed")
    with authorization_scope(AuthorizationContext("admin", "admin")):
        assert recover_target(runtime, "test", "Reviewed")["recovered"]


def test_durable_witness_is_written_before_native_ack(tmp_path):
    from .test_agent_native_target import target, spec
    adapter = target(tmp_path)
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": adapter})
    try:
        task = runtime.submit(spec())
        frame = runtime.observe(task.task_id)
        runtime.act(task.task_id, {"tool": "AC_increment", "arguments": {"hold": True},
                                   "observation_id": frame.observation_id})
        data = json.loads((tmp_path / "input.lock.journal").read_text(encoding="utf-8"))
        assert data["owner"] and data["held"]["keys"] == [{"keycode": 65, "is_shift": False}]
        runtime.pause(task.task_id)
        data = json.loads((tmp_path / "input.lock.journal").read_text(encoding="utf-8"))
        assert not data["owner"] and not data["held"]
    finally:
        runtime.close()


def test_stale_journal_blocks_adapter_without_spawning_or_erasing(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime import native_target
    resource = tmp_path / "input.lock"
    journal = InputJournal(resource)
    journal.acquire()
    before = journal.path.read_bytes()
    adapter = NativeDesktopTarget(resource_path=resource)
    monkeypatch.setattr(native_target, "owned_channel", lambda *a, **k: pytest.fail("unreviewed helper spawned"))
    with pytest.raises(AgentTaskError, match="explicit crash recovery"):
        adapter._ensure()
    adapter.cleanup()
    assert journal.path.read_bytes() == before


def test_host_process_death_leaves_a_gate_instead_of_replaying_input(tmp_path):
    import subprocess
    import sys
    from .test_agent_native_target import HELPER, spec
    resource = tmp_path / "input.lock"
    program = (
        "import os,sys\n"
        "from pathlib import Path\n"
        "from je_auto_control.utils.agent_runtime import AgentRuntime\n"
        "from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget\n"
        f"adapter=NativeDesktopTarget(argv=[sys.executable,'-u','-c',{HELPER!r}], resource_path=Path({str(resource)!r}))\n"
        f"runtime=AgentRuntime(Path({str(tmp_path / 'tasks.sqlite')!r}),targets={{'fixture':adapter}})\n"
        f"task=runtime.submit({spec()!r})\n"
        "frame=runtime.observe(task.task_id)\n"
        "runtime.act(task.task_id,{'tool':'AC_increment','arguments':{'hold':True},"
        "'observation_id':frame.observation_id})\n"
        "os._exit(0)\n"
    )
    result = subprocess.run([sys.executable, "-c", program], capture_output=True, timeout=20, check=False)
    assert result.returncode == 0, result.stderr
    journal = InputJournal(resource)
    assert journal.read()["held"]["keys"]
    with pytest.raises(AgentTaskError, match="explicit crash recovery"):
        journal.acquire()
    assert journal.recover("Reviewed fixture-only process death", lambda: None, "test-host")["recovered"]
