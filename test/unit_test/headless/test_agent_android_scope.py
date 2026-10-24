"""Device/app identity parsing and actual POSIX shell guards use only test-owned files and functions."""
import os
import shutil
import socket
import struct
import subprocess
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from je_auto_control.utils.agent_runtime.android_commands import ACTION_MARKER, compile_android_action
from je_auto_control.utils.agent_runtime.android_scope import (
    AndroidSnapshot, IDENTITY_MARKER, parse_android_snapshot)
from je_auto_control.android.adb_client import AndroidDevice
from je_auto_control.utils.agent_runtime.android_scope import IDENTITY_PROBE
from je_auto_control.utils.agent_runtime.android_session import AndroidDeviceSession
from je_auto_control.utils.agent_runtime.android_transport import AdbShellResult, ManagedAdbServer
from je_auto_control.utils.agent_runtime.errors import AgentHumanReview, AgentTaskError

DEVICE = "reviewed-device"
PACKAGE = "org.example.app"
BOOT = "11111111-2222-3333-4444-555555555555"
WINDOW = "Window{abc123 u0 org.example.app/.MainActivity}"
ACTIVITY = "ActivityRecord{def456 u0 org.example.app/.MainActivity t17}"
WM = f"  mTopFocusedDisplayId=0\n  mCurrentFocus={WINDOW}\n  mFocusedApp={ACTIVITY}\n"


def evidence(*, device=DEVICE, boot=BOOT, dump=WM):
    return f"{IDENTITY_MARKER}\n{device}\n{boot}\n{dump}".encode()


@pytest.fixture
def snapshot():
    return parse_android_snapshot(evidence(), DEVICE, PACKAGE)


def test_only_validated_identity_is_published_not_the_raw_window_dump(snapshot):
    private_dump = WM + "  private-title=must-not-be-published\n"
    observed = parse_android_snapshot(evidence(dump=private_dump), DEVICE, PACKAGE)
    assert observed == snapshot
    assert "must-not-be-published" not in str(observed.identity())
    assert observed.identity()["display"] == 0


@pytest.mark.parametrize("content", [
    b"", b"not-a-marker\na\nb\n", b"\xff", b"\0", b"x" * 262145,
    evidence(device="another-device"), evidence(boot="not-a-boot"),
    evidence(dump=WM.replace("mTopFocusedDisplayId=0", "mTopFocusedDisplayId=1")),
    evidence(dump=WM + f"  mCurrentFocus={WINDOW}\n"), evidence(dump=WM + "  mCurrentFocus=\n"),
    evidence(dump=WM.replace(WINDOW, "null")), evidence(dump=WM.replace(PACKAGE, "org.other.app")),
    evidence(dump=WM.replace("u0", "u10")), evidence(dump=WM.replace("mFocusedApp=", "oldFocusedApp=")),
], ids=lambda value: f"bytes-{len(value)}")
def test_unknown_or_ambiguous_snapshot_never_establishes_scope(content):
    with pytest.raises(AgentTaskError):
        parse_android_snapshot(content, DEVICE, PACKAGE)


@pytest.mark.parametrize("changes", [
    {"physical_id": "x; command"}, {"package": "org.example.app;evil"}, {"user": True},
    {"boot_id": BOOT.upper().replace("1", "A")}, {"window": "Window{bad}"},
    {"activity": ACTIVITY.replace("org.example.app", "org.other.app")},
])
def test_direct_snapshot_construction_has_the_same_boundary_validation(snapshot, changes):
    with pytest.raises(AgentTaskError):
        replace(snapshot, **changes)


@pytest.fixture
def run_guard(tmp_path, snapshot):
    shell = shutil.which("sh")
    if shell is None and os.name == "nt" and (git := shutil.which("git")):
        candidate = Path(git).parent.parent / "bin/sh.exe"
        shell = str(candidate) if candidate.is_file() else None
    if shell is None:
        pytest.skip("actual shell contract needs an installed POSIX sh")
    for name, content in (("device", DEVICE + "\n"), ("boot", BOOT + "\n"), ("wm", WM)):
        (tmp_path / name).write_text(content, encoding="utf-8", newline="")
    harness = '''
fixture_getprop() { command cat "$FIXTURE_DIR/device"; }
fixture_cat() { command cat "$FIXTURE_DIR/boot"; }
fixture_dumpsys() { command cat "$FIXTURE_DIR/wm"; }
fixture_input() {
    printf '%s\\n' "$@" >> "$FIXTURE_DIR/actions"
    if [ -f "$FIXTURE_DIR/after" ]; then command cat "$FIXTURE_DIR/after" > "$FIXTURE_DIR/wm"; fi
    if [ -f "$FIXTURE_DIR/fail" ]; then return 1; fi
}
'''

    def execute(name="AC_android_tap", arguments=None, *, probe=False):
        script = IDENTITY_PROBE if probe else compile_android_action(
            snapshot, name, {"x": 10, "y": 20} if arguments is None else arguments)
        for tool in ("getprop", "cat", "dumpsys", "input"):
            script = script.replace("/system/bin/" + tool, "fixture_" + tool)
        script = script.replace("/system/bin/printf", "printf").replace("/system/bin/sed", "sed")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        return subprocess.run([shell, "-c", harness + script], capture_output=True, timeout=5,
                              env={**os.environ, "FIXTURE_DIR": tmp_path.as_posix()}, cwd=tmp_path,
                              creationflags=flags, check=False)

    return execute


def test_guard_executes_one_finite_input_with_only_fixed_success_output(run_guard, tmp_path):
    result = run_guard()
    assert result.returncode == 0
    assert result.stdout == ACTION_MARKER
    assert result.stderr == b""
    assert (tmp_path / "actions").read_text().splitlines() == ["-d", "0", "tap", "10", "20"]


def test_fixed_probe_script_round_trips_through_actual_shell(run_guard, snapshot):
    result = run_guard(probe=True)
    assert result.returncode == 0
    assert parse_android_snapshot(result.stdout, DEVICE, PACKAGE) == snapshot


@pytest.mark.parametrize("name,arguments,body", [
    ("AC_android_swipe", {"x1": 1, "y1": 2, "x2": 3, "y2": 4}, ["swipe", "1", "2", "3", "4", "250"]),
    ("AC_android_key", {"key": "KEYCODE_ENTER"}, ["keyevent", "ENTER"]),
])
def test_other_finite_inputs_have_no_implicit_device_or_command_override(run_guard, tmp_path, name, arguments, body):
    result = run_guard(name, arguments)
    assert result.returncode == 0
    assert (tmp_path / "actions").read_text().splitlines() == ["-d", "0", *body]


def test_input_failure_never_emits_success_or_repeats_the_action(run_guard, tmp_path):
    (tmp_path / "fail").touch()
    result = run_guard()
    assert result.returncode == 94
    assert result.stdout == b""
    assert (tmp_path / "actions").read_text().splitlines().count("tap") == 1


@pytest.mark.parametrize("name,content,code", [
    ("device", "different-device\n", 91), ("boot", BOOT.replace("1", "2") + "\n", 92),
    ("wm", WM.replace(PACKAGE, "org.other.app"), 93),
    ("wm", WM.replace("mTopFocusedDisplayId=0", "mTopFocusedDisplayId=2"), 93),
    ("wm", WM + f"  mCurrentFocus={WINDOW}\n", 93),
    ("wm", WM + "  mCurrentFocus=\n", 93), ("wm", WM + "  mTopFocusedDisplayId=\n", 93),
    ("wm", WM.replace("u0", "u1"), 93),
])
def test_changed_reused_endpoint_or_ambiguous_scope_refuses_before_input(run_guard, tmp_path, name, content, code):
    (tmp_path / name).write_text(content, encoding="utf-8", newline="")
    result = run_guard()
    assert result.returncode == code
    assert result.stdout == b""
    assert not (tmp_path / "actions").exists()


def test_scope_change_after_action_is_not_published_as_confirmed_completion(run_guard, tmp_path):
    (tmp_path / "after").write_text(WM.replace(PACKAGE, "org.other.app"), encoding="utf-8", newline="")
    result = run_guard()
    assert result.returncode == 93
    assert result.stdout == b""
    assert (tmp_path / "actions").read_text().splitlines().count("tap") == 1


def test_typed_metacharacters_are_literal_and_never_evaluated(run_guard, tmp_path):
    value = "quote'\"; $(touch injected) `touch injected` $HOME"
    result = run_guard("AC_android_text", {"text": value})
    assert result.returncode == 0
    assert result.stdout == ACTION_MARKER
    assert (tmp_path / "actions").read_text().splitlines() == ["-d", "0", "text", value.replace(" ", "%s")]
    assert not (tmp_path / "injected").exists()


@pytest.mark.parametrize("name,arguments", [
    ("AC_android_shell", {"command": "arbitrary"}), (None, {}), ([], {}),
    ("AC_android_tap", {"x": True, "y": 0}), ("AC_android_tap", {"x": 0, "y": 16384}),
    ("AC_android_tap", {"x": -1, "y": 0}), ("AC_android_tap", {"x": 0.0, "y": 0}),
    ("AC_android_tap", {"x": 0, "y": 0, "serial": "other"}),
    ("AC_android_swipe", {"x1": 0, "y1": 0, "x2": 2, "y2": 2, "duration_ms": 2001}),
    ("AC_android_key", {"key": "HOME"}), ("AC_android_key", {"key": "POWER"}),
    ("AC_android_key", {"key": "BACK; arbitrary"}), ("AC_android_text", {"text": "literal%s"}),
    ("AC_android_text", {"text": "不可猜測 IME"}), ("AC_android_text", {"text": "line\ntext"}),
    ("AC_android_text", {"text": "x" * 1025}),
])
def test_unreviewed_tools_arguments_and_lossy_text_are_refused(snapshot, name, arguments):
    with pytest.raises(AgentTaskError):
        compile_android_action(snapshot, name, arguments)


class Server:
    def __init__(self):
        self.rows = [AndroidDevice("reviewed-endpoint", "device", transport_id="42")]
        self.result = AdbShellResult(evidence(), b"", 0)
        self.calls = []

    def list_devices(self, **_kwargs):
        self.calls.append("devices")
        return self.rows

    def shell(self, transport, command, **_kwargs):
        self.calls.append((transport, command))
        assert command == IDENTITY_PROBE
        return self.result


def session(server):
    return AndroidDeviceSession(server, serial="reviewed-endpoint", physical_id=DEVICE, package=PACKAGE)


def test_proposal_only_queries_identity_and_never_dispatches_input():
    server = Server()
    proposal = session(server).propose("AC_android_tap", {"x": 10, "y": 20})
    assert proposal.input_authorized is False
    assert proposal.transport_id == 42
    assert proposal.snapshot.physical_id == DEVICE
    assert server.calls == ["devices", (42, IDENTITY_PROBE)]


@pytest.mark.parametrize("rows", [[], [AndroidDevice("unreviewed", "device", transport_id="42")],
    [AndroidDevice("reviewed-endpoint", "unauthorized", transport_id="42")],
    [AndroidDevice("reviewed-endpoint", "device", transport_id=None)],
    [AndroidDevice("reviewed-endpoint", "device", transport_id="0")],
    [AndroidDevice("reviewed-endpoint", "device", transport_id=str(2**64))],
    [AndroidDevice("reviewed-endpoint", "device", transport_id="42;command")],
    [AndroidDevice("reviewed-endpoint", "device", transport_id="42")] * 2])
def test_selection_never_falls_back_to_first_device_or_ambiguous_transport(rows):
    server = Server()
    server.rows = rows
    with pytest.raises(AgentTaskError):
        session(server).inspect()
    assert server.calls == ["devices"]


def test_existing_session_never_adopts_a_new_boot():
    server = Server()
    adapter = session(server)
    adapter.inspect()
    server.result = replace(server.result, stdout=evidence(boot=BOOT.replace("1", "2")))
    with pytest.raises(AgentHumanReview, match="boot changed"):
        adapter.inspect()
    assert adapter._boot == BOOT


def test_server_reused_transport_must_still_identify_the_reviewed_physical_device():
    server = Server()
    adapter = session(server)
    adapter.inspect()
    server.result = replace(server.result, stdout=evidence(device="another-device"))
    with pytest.raises(AgentTaskError, match="physical device"):
        adapter.inspect()
    assert adapter._boot == BOOT


def test_bad_tool_arguments_are_refused_without_even_querying_the_server():
    server = Server()
    with pytest.raises(AgentTaskError):
        session(server).propose("AC_android_shell", {"command": "arbitrary"})
    assert not server.calls


def test_remote_probe_diagnostics_cannot_escape_as_task_errors():
    server = Server()
    server.result = AdbShellResult(evidence(), b"private-untrusted-diagnostic", 1)
    with pytest.raises(AgentTaskError) as caught:
        session(server).inspect()
    assert "private-untrusted-diagnostic" not in str(caught.value)


def test_inspection_shares_one_deadline_instead_of_renewing_it_for_shell(monkeypatch):
    from je_auto_control.utils.agent_runtime import android_session
    clock = [0.0]
    monkeypatch.setattr(android_session.time, "monotonic", lambda: clock[0])

    class TimedServer(Server):
        def list_devices(self, **kwargs):
            assert kwargs["timeout"] == 5
            clock[0] = 4.5
            return super().list_devices(**kwargs)

        def shell(self, transport, command, **kwargs):
            assert kwargs["timeout"] == 0.5
            return super().shell(transport, command, **kwargs)

    assert session(TimedServer()).inspect()[0] == 42


def test_expired_discovery_cannot_get_another_shell_budget_or_pin_boot(monkeypatch):
    from je_auto_control.utils.agent_runtime import android_session
    clock = [0.0]
    monkeypatch.setattr(android_session.time, "monotonic", lambda: clock[0])

    class ExpiredServer(Server):
        def list_devices(self, **kwargs):
            clock[0] = 5.1
            return super().list_devices(**kwargs)

    server = ExpiredServer()
    adapter = session(server)
    with pytest.raises(AgentTaskError, match="deadline exhausted"):
        adapter.inspect()
    assert server.calls == ["devices"]
    assert adapter._boot is None


def _serve_identity_wire(remote, device, services, failures):
    try:
        with remote, remote.makefile("rwb") as stream:
            service = stream.read(int(stream.read(4), 16))
            services.append(service)
            if service == b"host:devices-l":
                rows = b"reviewed-endpoint device transport_id:42\n"
                stream.write(b"OKAY" + f"{len(rows):04x}".encode() + rows)
                stream.flush()
                return
            assert service == b"host:transport-id:42"
            stream.write(b"OKAY")
            stream.flush()
            service = stream.read(int(stream.read(4), 16))
            assert service == b"shell,v2,raw:" + IDENTITY_PROBE.encode()
            services.append(service)
            stream.write(b"OKAY")
            stream.flush()
            assert stream.read(5) == struct.pack("<BI", 4, 0)
            output = evidence(device=device)
            stream.write(struct.pack("<BI", 1, len(output)) + output + struct.pack("<BI", 3, 1) + b"\0")
            stream.flush()
    except Exception as error:  # reason: surface owned fixture thread failures in the parent test
        failures.append(error)


@pytest.mark.parametrize("device", [DEVICE, "another-device"])
def test_session_uses_actual_adb_wire_protocol_for_readonly_identity_before_proposal(monkeypatch, device):
    workers, failures, services = [], [], []

    def connect(endpoint, *, timeout):
        assert endpoint == ("127.0.0.1", 54321)
        client, remote = socket.socketpair()
        remote.settimeout(timeout)

        worker = threading.Thread(target=_serve_identity_wire, args=(remote, device, services, failures),
                                  daemon=True)
        workers.append(worker)
        worker.start()
        return client

    monkeypatch.setattr(socket, "create_connection", connect)
    adapter = session(ManagedAdbServer("127.0.0.1", 54321))
    try:
        if device == DEVICE:
            assert adapter.propose("AC_android_tap", {"x": 1, "y": 2}).input_authorized is False
        else:
            with pytest.raises(AgentTaskError, match="physical device"):
                adapter.propose("AC_android_tap", {"x": 1, "y": 2})
    finally:
        for worker in workers:
            worker.join(timeout=2)
            assert not worker.is_alive()
        assert not failures
    assert len(workers) == 2
    assert services[0] == b"host:devices-l"
    assert not any(b"/system/bin/input" in item for item in services)


def test_concurrent_inspection_cannot_commit_two_different_boots_into_one_session():
    barrier = threading.Barrier(2)
    successes, reviews = [], []

    class ConcurrentServer(Server):
        def shell(self, transport, command, **_kwargs):
            assert transport == 42 and command == IDENTITY_PROBE
            boot = BOOT if threading.current_thread().name == "old-boot" else BOOT.replace("1", "2")
            return AdbShellResult(evidence(boot=boot), b"", 0)

    adapter = session(ConcurrentServer())

    def inspect():
        try:
            successes.append(adapter.inspect(check=lambda: barrier.wait(timeout=2))[1].boot_id)
        except AgentHumanReview:
            reviews.append(True)

    threads = [threading.Thread(target=inspect, name=name) for name in ("old-boot", "new-boot")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)
        assert not thread.is_alive()
    assert len(successes) == 1
    assert len(reviews) == 1
    assert adapter._boot == successes[0]


def test_proposal_refuses_combined_quoted_input_and_scope_above_the_transport_limit(snapshot):
    expanded = replace(snapshot, window=f"Window{{abc123 u0 {PACKAGE}/.{('A' * 450)}}}",
                       activity=f"ActivityRecord{{def456 u0 {PACKAGE}/.{('A' * 440)} t17}}")
    with pytest.raises(AgentTaskError, match="limit|bounded"):
        compile_android_action(expanded, "AC_android_text", {"text": "'" * 1024})


def test_host_proposal_cannot_accidentally_publish_command_text_as_a_json_task_payload():
    from je_auto_control.utils.agent_runtime.models import detached
    proposal = session(Server()).propose("AC_android_text", {"text": "fixture-private-text"})
    assert "fixture-private-text" not in repr(proposal)
    with pytest.raises(AgentTaskError):
        detached(proposal)
    with pytest.raises(AttributeError):
        proposal.input_authorized = True
