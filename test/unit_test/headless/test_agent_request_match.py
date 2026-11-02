"""Destination request hashes bind recovery inspection to the accepted specification."""
import copy
from concurrent.futures import CancelledError

import pytest

from headless.test_agent_runtime import FakeTarget, specification
from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
from je_auto_control.utils.agent_runtime.service import AgentRuntimeService
from je_auto_control.utils.rbac.authorization import AuthorizationContext, AuthorizationError, authorization_scope


def test_matching_normalizes_defaults_and_destination_roots_without_dispatch(tmp_path):
    target = FakeTarget()
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": target})
    root = tmp_path / "artifacts"
    (root / "child").mkdir(parents=True)
    spec = specification(roots=[str(root)])
    try:
        accepted = runtime.submit(spec, idempotency_key="key")
        expected = spec.to_dict()
        expected["roots"] = [str(root / "child" / "..")]
        expected = dict(reversed(list(expected.items())))
        match = runtime.lookup("key", expected)
        assert match["spec_match_contract"] == 1 and match["spec_match"] == "matches"
        assert match["task"]["task_id"] == accepted.task_id
        assert target.calls == [] and not runtime._leases
        assert len(runtime.list()) == 1
    finally:
        runtime.close()


@pytest.mark.parametrize("change", ["goal", "actions", "inputs", "budget", "mode", "criteria"])
def test_changed_reviewed_spec_is_reported_without_resubmission(tmp_path, change):
    target = FakeTarget()
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": target})
    expected = specification().to_dict()
    try:
        accepted = runtime.submit(copy.deepcopy(expected), idempotency_key="key")
        if change == "goal":
            expected["goal"] = "different task"
        elif change == "actions":
            expected["actions"] = [{"tool": "AC_increment", "arguments": {"amount": 2}}]
        elif change == "inputs":
            expected["inputs"] = {"value": "changed"}
        elif change == "budget":
            expected["budget"]["max_steps"] = 24
        elif change == "mode":
            expected["mode"] = "skill"
        else:
            expected["success_criteria"][0]["value"] = 2
        result = runtime.lookup("key", expected)
        assert result["found"] is True and result["spec_match"] == "differs"
        assert result["task"]["task_id"] == accepted.task_id
        assert target.calls == [] and not runtime._leases and len(runtime.list()) == 1
    finally:
        runtime.close()


def test_lookup_remains_readable_but_matching_is_unverifiable_when_target_is_absent(tmp_path):
    path = tmp_path / "tasks.sqlite"
    runtime = AgentRuntime(path, targets={"fixture": FakeTarget()})
    accepted = runtime.submit(specification(), idempotency_key="key")
    runtime.close()
    replacement = AgentRuntime(path, targets={})
    try:
        result = replacement.lookup("key", specification())
        assert result["found"] is True and result["task"]["task_id"] == accepted.task_id
        assert result["spec_match"] == "unverifiable"
        assert not replacement._leases
    finally:
        replacement.close()


def test_spec_match_does_not_search_another_owner_or_create_missing_requests(tmp_path):
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": FakeTarget()})
    try:
        with authorization_scope(AuthorizationContext("alice", "operator")):
            runtime.submit(specification(), idempotency_key="key")
        with authorization_scope(AuthorizationContext("bob", "operator")):
            result = runtime.lookup("key", specification())
            assert result["found"] is False and result["spec_match"] == "not_found"
        assert len(runtime.list()) == 1
    finally:
        runtime.close()


def test_http_spec_match_is_closed_and_never_dispatches(tmp_path):
    service = AgentRuntimeService(tmp_path, targets={"fixture": FakeTarget()})
    service.start()
    client = AgentRuntimeClient(tmp_path / "agent_runtime.json")
    try:
        original = specification().to_dict()
        accepted = client.call("submit", {"spec": original, "idempotency_key": "key"})
        result = client.call("lookup", {"idempotency_key": "key", "spec": original})
        assert result["spec_match"] == "matches" and result["task"]["task_id"] == accepted["task_id"]
        assert not service.runtime._leases and service.runtime.store.actions(accepted["task_id"]) == []
        for invalid in (None, [], {"unknown": True}):
            with pytest.raises(AgentTaskError):
                client.call("lookup", {"idempotency_key": "key", "spec": invalid})
        with pytest.raises(AgentTaskError):
            client.call("lookup", {"idempotency_key": "key", "spec": original, "resume": True})
        assert len(service.runtime.list()) == 1
    finally:
        service.close()


@pytest.mark.parametrize("error", [AuthorizationError("revoked"), CancelledError()])
def test_matching_preserves_authority_and_cancellation_controls(tmp_path, monkeypatch, error):
    runtime = AgentRuntime(tmp_path / "tasks.sqlite", targets={"fixture": FakeTarget()})
    try:
        runtime.submit(specification(), idempotency_key="key")

        def reject(_spec):
            raise error

        monkeypatch.setattr(runtime, "_validated_spec", reject)
        with pytest.raises(type(error)):
            runtime.lookup("key", specification())
        assert not runtime._leases
    finally:
        runtime.close()


def test_cli_optional_spec_is_forwarded_to_read_only_lookup(monkeypatch):
    import argparse
    from je_auto_control.utils.agent_runtime import cli

    parser = argparse.ArgumentParser()
    cli.register_parser(parser.add_subparsers(), lambda *_args: 0)
    arguments = parser.parse_args(["agent-task", "lookup", "key", "--spec", "reviewed.json"])
    expected = specification().to_dict()
    calls = []
    monkeypatch.setattr(cli, "_read", lambda _path: expected)
    monkeypatch.setattr(cli.api, "lookup_agent_task", lambda *args: calls.append(args) or {"found": False})
    assert cli.run(arguments) == {"found": False}
    assert calls == [("key", expected)]
