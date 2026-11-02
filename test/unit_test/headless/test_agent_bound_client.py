"""Pinned local clients fail before transport when the source endpoint, credential or generation changes."""
import json
from unittest.mock import Mock

import pytest

from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
from je_auto_control.utils.agent_runtime.errors import AgentTaskError


@pytest.fixture
def connection(tmp_path, monkeypatch):
    path = tmp_path / "connection.json"
    metadata = {"url": "http://127.0.0.1:23987", "token": "fixture-private-bearer", "generation": "fixture-generation"}
    path.write_text(json.dumps(metadata))
    transport = Mock(return_value={"state": "fixture"})
    monkeypatch.setattr("je_auto_control.utils.agent_runtime.client.request_json", transport)
    return path, metadata, transport


@pytest.mark.parametrize("field,value", [("url", "http://127.0.0.1:23988"), ("token", "replacement"),
                                         ("generation", "new-generation")])
def test_changed_source_identity_never_retargets_a_bound_operation(connection, field, value):
    path, metadata, transport = connection
    bound = AgentRuntimeClient(path).bound()
    path.write_text(json.dumps({**metadata, field: value}))
    with pytest.raises(AgentTaskError, match="connection changed"):
        bound.call("submit", {"spec": {}})
    with pytest.raises(AgentTaskError, match="connection changed"):
        bound.bound()
    transport.assert_not_called()
    assert metadata["token"] not in repr(vars(bound))


def test_bound_client_keeps_an_absolute_path_and_does_not_cache_credentials(connection, monkeypatch, tmp_path):
    path, metadata, transport = connection
    monkeypatch.chdir(tmp_path)
    client = AgentRuntimeClient(path.name).bound()
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)
    assert client.call("get", {"task_id": "fixture"}) == {"state": "fixture"}
    assert transport.call_args.args[0] == metadata["url"] + "/agent/task?task_id=fixture"
    assert metadata["token"] not in repr(vars(client))


def test_legacy_ordinary_client_stays_adaptive_but_binding_requires_a_generation(connection):
    path, metadata, transport = connection
    metadata.pop("generation")
    path.write_text(json.dumps(metadata))
    client = AgentRuntimeClient(path)
    assert client.call("list") == {"state": "fixture"}
    transport.reset_mock()
    with pytest.raises(AgentTaskError, match="service generation"):
        client.bound()
    transport.assert_not_called()


@pytest.mark.parametrize("value", [[], {"url": None}, {"url": "http://[broken", "token": "fixture"},
                                  {"url": "http://127.0.0.1?redirect=other", "token": "fixture"},
                                  {"url": "http://user@127.0.0.1", "token": "fixture"},
                                  {"url": "http://127.0.0.1", "token": []}])
def test_malformed_local_metadata_is_a_typed_failure_without_transport(connection, value):
    path, _metadata, transport = connection
    path.write_text(json.dumps(value))
    with pytest.raises(AgentTaskError, match="connection metadata"):
        AgentRuntimeClient(path).call("list")
    transport.assert_not_called()
