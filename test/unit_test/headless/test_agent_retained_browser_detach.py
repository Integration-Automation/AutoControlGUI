"""The original host releases input resources only after the exact owned helper retires input."""
from types import SimpleNamespace

import pytest

from headless.test_agent_browser_target import profile
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.native_target import NativeDesktopTarget

PROOF = {"contract": 1, "input_supported": False, "network_retired": True, "context_id": "b" * 32}


@pytest.fixture
def owned(tmp_path):
    events = []

    class Channel:
        retired = False
        response = dict(PROOF)
        bootstrap = {"protocol": 1, "browser_readonly": 1}

        def request(self, operation, payload, **_options):
            events.append(operation)
            if operation == "bootstrap":
                assert payload == {}
                return self.bootstrap
            assert operation == "retire_browser" and payload == {}
            if isinstance(self.response, Exception):
                raise self.response
            return self.response

        def close(self):
            self.retired = True
            events.append("process-reaped")

    target = NativeDesktopTarget(profile=profile().to_dict(), resource_path=tmp_path / "owned.lock")
    channel = Channel()
    target._channel = channel
    target._journal = SimpleNamespace(update=lambda *_args: events.append("journal-update"),
                                      release=lambda: events.append("journal-release"))
    target._resource = SimpleNamespace(close=lambda: events.append("resource-close"))
    yield SimpleNamespace(target=target, channel=channel, events=events)
    channel.close()


def test_detach_transfers_actual_channel_after_proof_and_releases_only_input_resources(owned):
    channel, proof = owned.target.detach_readonly()
    assert channel is owned.channel and proof == PROOF
    assert owned.events == ["bootstrap", "journal-update", "retire_browser", "journal-release", "resource-close"]
    assert not channel.retired
    assert owned.target._channel is None
    assert owned.target._resource is None and owned.target._journal is None
    assert owned.target._pending is None


@pytest.mark.parametrize("damage", ["pending", "held-key", "no-resource", "no-journal"])
def test_unsettled_input_cannot_be_detached_or_falsely_released(owned, damage):
    target = owned.target
    if damage == "pending":
        target._pending = "perform"
    elif damage == "held-key":
        target._ledger.consume({"kind": "key_press", "keycode": 65})
    elif damage == "no-resource":
        target._resource = None
    else:
        target._journal = None
    with pytest.raises(AgentTaskError):
        target.detach_readonly()
    assert owned.events == []
    assert target._channel is owned.channel


def test_unsupported_sdk_keeps_original_normal_cleanup_owner(owned):
    owned.channel.response = {"supported": False}
    assert owned.target.detach_readonly() is None
    assert owned.target._channel is owned.channel and not owned.channel.retired
    assert owned.target._pending is None
    assert "journal-release" not in owned.events and "resource-close" not in owned.events


@pytest.mark.parametrize("response", [
    {"contract": True, "input_supported": False, "network_retired": True, "context_id": "b" * 32},
    {**PROOF, "input_supported": True}, {**PROOF, "network_retired": False},
    AgentTaskError("controlled retirement failed"),
])
def test_failed_or_forged_retirement_preserves_source_ownership_and_prevents_freeze_retry(owned, response):
    owned.channel.response = response
    with pytest.raises(AgentTaskError):
        owned.target.detach_readonly()
    assert owned.target._channel is owned.channel
    assert owned.target._resource is not None and owned.target._journal is not None
    assert owned.target._pending == "retire_browser"
    before = list(owned.events)
    owned.channel.response = dict(PROOF)
    with pytest.raises(AgentTaskError):
        owned.target.detach_readonly()
    assert owned.events == before


def test_detach_never_relaunches_an_absent_or_reaped_source_helper(owned, monkeypatch):
    monkeypatch.setattr(owned.target, "_launch", lambda *_args: pytest.fail("No replacement helper may launch"))
    owned.channel.retired = True
    assert owned.target.detach_readonly() is None
    assert owned.events == []


@pytest.mark.parametrize("version", [None, False, True, 0, 2, "1"])
def test_legacy_helper_capability_does_not_break_normal_browser_cleanup(owned, version):
    owned.channel.bootstrap = {"protocol": 1}
    if version is not None:
        owned.channel.bootstrap["browser_readonly"] = version
    assert owned.target.detach_readonly() is None
    assert owned.events == ["bootstrap"]
    assert owned.target._pending is None
    assert owned.target._channel is owned.channel and not owned.channel.retired
