"""Channel selection tests: no helper process, socket or service is ever started."""
import json
from pathlib import Path

import pytest

from je_auto_control.utils.agent_runtime import helper_owner_linux, native_channel
from je_auto_control.utils.agent_runtime import owned_channel_factory as factory
from je_auto_control.utils.agent_runtime.errors import AgentTaskError

ARGV = ["/usr/bin/python3", "-I", "-u", "-m", "je_auto_control.utils.agent_runtime.native_worker"]


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return ("local", args, kwargs)


class FakeTransport:
    def __init__(self, endpoint):
        self.endpoint = endpoint


@pytest.fixture
def local(monkeypatch):
    recorder = Recorder()
    monkeypatch.setattr(native_channel, "OwnedChannel", recorder)
    return recorder


def bind(monkeypatch, tmp_path, content, *, trusted=True):
    path = tmp_path / "owner_service.json"
    path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
    monkeypatch.setattr(factory, "BINDING_PATH", str(path))
    monkeypatch.setattr(factory, "_trusted", lambda _status: trusted)
    monkeypatch.setattr(factory.load_binding, "__defaults__", (str(path),))
    return path


VALID = {"endpoint": "/run/autocontrol/owner.sock", "policies": [{"argv": ARGV, "policy": 3}]}


def test_windows_and_macos_keep_the_local_channel(monkeypatch, tmp_path, local):
    bind(monkeypatch, tmp_path, VALID)
    for platform in ("win32", "darwin"):
        monkeypatch.setattr(factory.sys, "platform", platform)
        assert factory.owned_channel(ARGV)[0] == "local"
    assert len(local.calls) == 2


def test_linux_without_a_binding_keeps_the_local_channel(monkeypatch, tmp_path, local):
    monkeypatch.setattr(factory.sys, "platform", "linux")
    monkeypatch.setattr(factory.load_binding, "__defaults__", (str(tmp_path / "absent.json"),))
    control = object()
    assert factory.owned_channel(ARGV, on_control=control)[0] == "local"
    assert local.calls == [((ARGV,), {"on_control": control})]


def test_linux_binding_launches_only_through_the_owner_service(monkeypatch, tmp_path, local):
    bind(monkeypatch, tmp_path, VALID)
    monkeypatch.setattr(factory.sys, "platform", "linux")
    monkeypatch.setattr(helper_owner_linux, "SeqpacketTransport", FakeTransport)
    channel = factory.owned_channel(ARGV)
    assert isinstance(channel, helper_owner_linux.OwnerServiceChannel)
    assert channel._transport.endpoint == VALID["endpoint"] and channel._policy == 3 and channel._arguments == ()
    assert not local.calls


def test_linux_binding_without_an_exact_row_refuses_without_fallback(monkeypatch, tmp_path, local):
    bind(monkeypatch, tmp_path, VALID)
    monkeypatch.setattr(factory.sys, "platform", "linux")
    with pytest.raises(AgentTaskError, match="no policy"):
        factory.owned_channel(ARGV + ["--extra"])
    with pytest.raises(AgentTaskError, match="no policy"):
        factory.owned_channel(ARGV[:-1])
    assert not local.calls


@pytest.mark.parametrize("content", [
    "not json",
    {"endpoint": "/run/x.sock"},
    {"endpoint": "relative.sock", "policies": VALID["policies"]},
    {"endpoint": "/run/x.sock", "policies": []},
    {"endpoint": "/run/x.sock", "policies": [{"argv": ARGV, "policy": 32}]},
    {"endpoint": "/run/x.sock", "policies": [{"argv": ARGV, "policy": True}]},
    {"endpoint": "/run/x.sock", "policies": [{"argv": [], "policy": 1}]},
    {"endpoint": "/run/x.sock", "policies": [{"argv": ARGV, "policy": 1}, {"argv": ARGV, "policy": 2}]},
    {"endpoint": "/run/x.sock", "policies": [{"argv": ARGV, "policy": 1, "extra": 1}]},
    {"endpoint": "/run/x.sock", "policies": VALID["policies"], "fallback": True},
])
def test_malformed_binding_refuses(monkeypatch, tmp_path, content):
    path = bind(monkeypatch, tmp_path, content)
    with pytest.raises(AgentTaskError):
        factory.load_binding(str(path))


def test_untrusted_binding_refuses(monkeypatch, tmp_path):
    path = bind(monkeypatch, tmp_path, VALID, trusted=False)
    with pytest.raises(AgentTaskError, match="root-owned"):
        factory.load_binding(str(path))


def test_valid_binding_parses_exact_rows(monkeypatch, tmp_path):
    path = bind(monkeypatch, tmp_path, VALID)
    binding = factory.load_binding(str(path))
    assert binding.endpoint == VALID["endpoint"] and binding.policies == {tuple(ARGV): 3}


def test_every_consumer_obtains_its_channel_through_the_factory():
    package = Path(factory.__file__).parent
    for name in ("helper_environment.py", "native_target.py", "remote_target.py", "presence_pool.py",
                 "presence_worker.py"):
        source = (package / name).read_text(encoding="utf-8")
        assert "owned_channel" in source and "OwnedChannel(" not in source, name


def test_nested_grant_reaches_the_service_channel_and_refuses_elsewhere(monkeypatch, tmp_path, local):
    from je_auto_control.utils.agent_runtime.owner_service_nested import NestedGrant
    grant = NestedGrant(((142, 1), (0, 3)), bytes(32))
    bind(monkeypatch, tmp_path, VALID)
    monkeypatch.setattr(factory.sys, "platform", "linux")
    monkeypatch.setattr(helper_owner_linux, "SeqpacketTransport", FakeTransport)
    assert factory.owned_channel(ARGV, nested=grant)._parent is grant
    monkeypatch.setattr(factory.sys, "platform", "win32")
    with pytest.raises(AgentTaskError, match="needs the Linux owner service"):
        factory.owned_channel(ARGV, nested=grant)
    assert not local.calls


@pytest.mark.parametrize("platform, status, containment", [
    ("win32", "not_probed", "windows_job_object"),
    ("darwin", "not_supported", "process_group"),
    ("freebsd14", "not_supported", "process_group"),
])
def test_containment_status_outside_linux(monkeypatch, platform, status, containment):
    monkeypatch.setattr(factory.sys, "platform", platform)
    result = factory.helper_containment()
    assert result == {"native_evidence": "not_recorded", "mode": "local", "intended_containment": containment,
                      "status": status}


def test_containment_status_on_linux_never_claims_native_evidence(monkeypatch, tmp_path):
    monkeypatch.setattr(factory.sys, "platform", "linux")
    monkeypatch.setattr(factory.load_binding, "__defaults__", (str(tmp_path / "absent.json"),))
    assert factory.helper_containment()["status"] == "not_configured"
    bind(monkeypatch, tmp_path, {"endpoint": "relative"})
    refused = factory.helper_containment()
    assert refused["status"] == "binding_refused" and refused["mode"] == "owner_service" and refused["reason"]
    bind(monkeypatch, tmp_path, VALID)
    for reachable, status in ((False, "unreachable"), (True, "reachable_unverified")):
        monkeypatch.setattr(factory, "_endpoint_reachable", lambda _endpoint, value=reachable: value)
        result = factory.helper_containment()
        assert result["status"] == status and result["policies"] == 1
        assert result["native_evidence"] == "not_recorded"


def test_runtime_status_carries_the_containment_section(monkeypatch, tmp_path):
    from je_auto_control.utils.agent_runtime import api
    monkeypatch.setattr(api, "default_connection_path", lambda: tmp_path / "absent.json")
    status = api.agent_runtime_status()
    assert status["configured"] is False and status["helper_containment"]["native_evidence"] == "not_recorded"
