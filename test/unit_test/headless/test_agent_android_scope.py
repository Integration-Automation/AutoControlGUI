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

from je_auto_control.utils.agent_runtime.android_commands import compile_android_action
from je_auto_control.utils.agent_runtime.android_action_result import ACTION_MARKER, parse_android_action_result
from je_auto_control.utils.agent_runtime.android_commands import (
    INPUT_MARKER, POLICY_MARKER, SAFETY_END, compile_android_input_probe)
from je_auto_control.utils.agent_runtime.android_geometry import AndroidRect, covers_android_path
from je_auto_control.utils.agent_runtime.android_input_evidence import parse_android_input_evidence
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
fixture_dumpsys() {
    if [ "$1" = input ]; then command cat "$FIXTURE_DIR/input";
    elif [ "$2" = policy ]; then command cat "$FIXTURE_DIR/policy";
    else command cat "$FIXTURE_DIR/wm"; fi
}
fixture_input() {
    printf '%s\\n' "$@" >> "$FIXTURE_DIR/actions"
    for field in device boot; do
        if [ -f "$FIXTURE_DIR/after-$field" ]; then
            command cat "$FIXTURE_DIR/after-$field" > "$FIXTURE_DIR/$field"
        fi
    done
    if [ -f "$FIXTURE_DIR/after" ]; then command cat "$FIXTURE_DIR/after" > "$FIXTURE_DIR/wm"; fi
    if [ -f "$FIXTURE_DIR/fail" ]; then return 1; fi
}
'''

    def execute(name="AC_android_tap", arguments=None, *, probe=False, input_evidence=None):
        if probe == "input":
            script = compile_android_input_probe(snapshot)
        elif probe:
            script = IDENTITY_PROBE
        else:
            script = compile_android_action(snapshot, name,
                {"x": 10, "y": 20} if arguments is None else arguments, input_evidence=input_evidence)
        for tool in ("getprop", "cat", "dumpsys", "input"):
            script = script.replace("/system/bin/" + tool, "fixture_" + tool)
        script = script.replace("/system/bin/printf", "printf").replace("/system/bin/sed", "sed")
        script = script.replace("/system/bin/sha256sum", "sha256sum").replace("/system/bin/cut", "cut")
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
    parsed = parse_android_action_result(AdbShellResult(result.stdout, result.stderr, result.returncode))
    assert parsed.phase == "input_failed"
    assert parsed.may_have_effect
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
    parsed = parse_android_action_result(AdbShellResult(result.stdout, result.stderr, result.returncode))
    assert parsed.phase == "pre_input_refused"
    assert not parsed.may_have_effect
    assert not (tmp_path / "actions").exists()


def test_scope_change_after_action_is_not_published_as_confirmed_completion(run_guard, tmp_path):
    (tmp_path / "after").write_text(WM.replace(PACKAGE, "org.other.app"), encoding="utf-8", newline="")
    result = run_guard()
    assert result.returncode == 93
    parsed = parse_android_action_result(AdbShellResult(result.stdout, result.stderr, result.returncode))
    assert parsed.phase == "post_input_refused"
    assert parsed.may_have_effect
    assert (tmp_path / "actions").read_text().splitlines().count("tap") == 1


@pytest.mark.parametrize("field,content,code", [
    ("device", "different-device\n", 91), ("boot", BOOT.replace("1", "2") + "\n", 92),
])
def test_identity_failure_after_input_never_masquerades_as_pre_input_refusal(run_guard, tmp_path, field, content, code):
    (tmp_path / ("after-" + field)).write_text(content, encoding="utf-8", newline="")
    result = run_guard()
    assert result.returncode == code
    parsed = parse_android_action_result(AdbShellResult(result.stdout, result.stderr, result.returncode))
    assert parsed.phase == "post_input_refused" and parsed.may_have_effect
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


def input_record(index=0, **changes):
    data = {"name": "abc123 org.example.app/.MainActivity", "id": 100 + index, "flags": "0x0",
        "alpha": "1.00", "frame": "[0,0][100,200]", "app": ACTIVITY, "app_token": "0x1110",
        "regions": "[0,0][100,200]", "pid": 1234, "uid": 10001, "token": "0x2220", **changes}
    return (f"      {index}: name='{data['name']}', id={data['id']}, displayId=0, "
        f"inputConfig={data['flags']}, alpha={data['alpha']}, frame={data['frame']}, globalScale=1.000000, "
        f"applicationInfo.name={data['app']}, applicationInfo.token={data['app_token']}, "
        f"touchableRegion={data['regions']}, ownerPid={data['pid']}, ownerUid={data['uid']}, "
        f"dispatchingTimeout=5000ms, hasToken={data['token']}, touchOcclusionMode=BLOCK_UNTRUSTED\n"
        "        transform (ROT_0) (IDENTITY)\n")


def input_dump(*records):
    name = "abc123 org.example.app/.MainActivity"
    return ("INPUT MANAGER (dumpsys input)\nInput Dispatcher State:\n  DispatchEnabled: true\n"
        "  DispatchFrozen: false\n  InputFilterEnabled: false\n  FocusedDisplayId: 0\n"
        f"  FocusedApplications:\n    displayId=0, name='{ACTIVITY}', dispatchingTimeout=5000ms\n"
        f"  FocusedWindows:\n    displayId=0, name='{name}'\n"
        f"  FocusRequests:\n    displayId=0, name='{name}' result='OK'\n"
        "  Pointer Capture Requested: false\n  Current Window with Pointer Capture: None\n"
        "  TouchStates: <no displays touched>\n  Display: 0\n    logicalSize=100x200\n"
        "        transform (ROT_0) (IDENTITY)\n    Windows:\n"
        + "".join(records or (input_record(),))
        + "  Global Monitors: <none>\n  RecentQueue: <empty>\n  PendingEvent: <none>\n"
        "  InboundQueue: <empty>\n  ReplacedKeys: <empty>\n  CommandQueue: <empty>\n  Connections:\n"
        f"    42: channelName='{name} (server)', windowName='{name} (server)', "
        "status=NORMAL, monitor=false, responsive=true\n"
        "      OutboundQueue: <empty>\n      WaitQueue: <empty>\n  AppSwitch: not pending\n"
        "  Configuration:\n    KeyRepeatDelay: 50ms\n").encode()


def policy_dump():
    return ("WINDOW MANAGER POLICY STATE (dumpsys window policy)\n    KeyguardServiceDelegate\n"
        "      showing=false\n      inputRestricted=false\n      occluded=false\n      secure=true\n"
        "      dreaming=false\n      systemIsReady=true\n      deviceHasKeyguard=true\n      enabled=true\n"
        "      offReason=OFF_BECAUSE_OF_USER\n      currentUser=0\n      bootCompleted=true\n"
        "      screenState=SCREEN_STATE_ON\n      interactiveState=INTERACTIVE_STATE_AWAKE\n"
        "      KeyguardStateMonitor\n        mIsShowing=false\n        mSimSecure=false\n"
        "        mInputRestricted=false\n        mTrusted=false\n        mCurrentUserId=0\n"
        "    Looper state:\n      private-clock=123\n").encode()


def test_current_native_input_evidence_binds_owner_but_still_grants_no_input(snapshot):
    proof = parse_android_input_evidence(input_dump(), policy_dump(), snapshot)
    proof.require_path((1, 1), (99, 199))
    assert proof.input_authorized is False
    assert proof.has_global_monitors is False
    assert proof.windows[0].owner == (1234, 10001)


@pytest.mark.parametrize("old,new", [
    ("DispatchEnabled: true", "DispatchEnabled: false"), ("DispatchFrozen: false", "DispatchFrozen: true"),
    ("InputFilterEnabled: false", "InputFilterEnabled: true"), ("FocusedDisplayId: 0", "FocusedDisplayId: 1"),
    ("Pointer Capture Requested: false", "Pointer Capture Requested: true"),
    ("TouchStates: <no displays touched>", "TouchStatesByDisplay:\n    0: down=true"),
    ("PendingEvent: <none>", "PendingEvent:\n    event-waiting"),
    ("InboundQueue: <empty>", "InboundQueue: length=1"), ("CommandQueue: <empty>", "CommandQueue: size=1"),
    ("WaitQueue: <empty>", "WaitQueue: length=1"), ("OutboundQueue: <empty>", "OutboundQueue: length=1"),
    ("responsive=true", "responsive=false"), ("status=NORMAL", "status=BROKEN"),
    ("AppSwitch: not pending", "AppSwitch: pending, due in 10ms"), ("result='OK'", "result='NOT_FOCUSABLE'"),
    ("    logicalSize=100x200", "    logicalSize=0x200"),
    ("        transform (ROT_0) (IDENTITY)\n    Windows:", "        transform (ROT_90) (ROTATE )\n    Windows:"),
    ("  Global Monitors: <none>", "    unparsed-foreign-window"),
])
def test_unsettled_or_unknown_dispatcher_state_is_refused(snapshot, old, new):
    with pytest.raises(AgentTaskError):
        parse_android_input_evidence(input_dump().replace(old.encode(), new.encode()), policy_dump(), snapshot)


@pytest.mark.parametrize("old,new", [
    ("showing=false", "showing=true"), ("inputRestricted=false", "inputRestricted=true"),
    ("occluded=false", "occluded=true"), ("dreaming=false", "dreaming=true"),
    ("bootCompleted=true", "bootCompleted=false"), ("currentUser=0", "currentUser=10"),
    ("mIsShowing=false", "mIsShowing=true"), ("mInputRestricted=false", "mInputRestricted=true"),
    ("mCurrentUserId=0", "mCurrentUserId=10"), ("SCREEN_STATE_ON", "SCREEN_STATE_OFF"),
    ("INTERACTIVE_STATE_AWAKE", "INTERACTIVE_STATE_SLEEP"),
    ("      showing=false", "      showing=false\n      showing=true"),
])
def test_either_locked_or_inconsistent_keyguard_view_refuses_input_evidence(snapshot, old, new):
    with pytest.raises(AgentTaskError):
        parse_android_input_evidence(input_dump(), policy_dump().replace(old.encode(), new.encode()), snapshot)


@pytest.mark.parametrize("changes", [
    {"flags": "NOT_FOCUSABLE"}, {"flags": "FUTURE_UNKNOWN_FLAG"}, {"alpha": "0.50"},
    {"regions": "<empty>"}, {"regions": "[0,0][0,200]"}, {"pid": 0}, {"uid": 110001},
    {"app": "another-app"}, {"token": "<null>"}, {"app_token": "<null>"},
])
def test_native_target_must_have_one_matching_live_app_channel(snapshot, changes):
    with pytest.raises(AgentTaskError):
        parse_android_input_evidence(input_dump(input_record(**changes)), policy_dump(), snapshot)


def test_whole_swipe_must_stay_in_region_union_not_just_its_endpoints(snapshot):
    proof = parse_android_input_evidence(input_dump(input_record(regions="[0,0][40,200]|[60,0][100,200]")),
                                         policy_dump(), snapshot)
    with pytest.raises(AgentTaskError, match="path leaves"):
        proof.require_path((10, 100), (90, 100))
    adjacent = parse_android_input_evidence(input_dump(input_record(regions="[0,0][50,200]|[50,0][100,200]")),
                                            policy_dump(), snapshot)
    adjacent.require_path((10, 100), (90, 100))


def test_overlay_in_swipe_interior_is_detected_and_irrelevant_bounding_box_overlap_is_allowed(snapshot):
    overlay = input_record(0, name="foreign-private-title", frame="[45,95][55,105]", regions="[45,95][55,105]")
    proof = parse_android_input_evidence(input_dump(overlay, input_record(1)), policy_dump(), snapshot)
    with pytest.raises(AgentTaskError, match="overlay"):
        proof.require_path((10, 100), (90, 100))
    assert "foreign-private-title" not in repr(proof)
    unrelated = overlay.replace("[45,95][55,105]", "[40,0][60,10]")
    proof = parse_android_input_evidence(input_dump(unrelated, input_record(1)), policy_dump(), snapshot)
    proof.require_path((0, 0), (99, 199))


def test_background_window_does_not_occlude_but_background_spy_still_receives_input(snapshot):
    behind = input_record(1, name="background", id=101)
    parse_android_input_evidence(input_dump(input_record(), behind), policy_dump(), snapshot).require_path((5, 5), (6, 6))
    spy = behind.replace("inputConfig=0x0", "inputConfig=SPY | TRUSTED_OVERLAY")
    with pytest.raises(AgentTaskError, match="foreign"):
        parse_android_input_evidence(input_dump(input_record(), spy), policy_dump(), snapshot).require_path((5, 5), (6, 6))


def test_history_and_old_anr_cannot_replace_current_input_or_renew_its_fingerprint(snapshot):
    live = input_dump()
    proof = parse_android_input_evidence(live, policy_dump(), snapshot)
    changed = live.replace(b"RecentQueue: <empty>", b"RecentQueue: length=1\n    historical-only")
    changed += b"\nInput Dispatcher State at time of last ANR:\n  DispatchEnabled: false\n"
    assert parse_android_input_evidence(changed, policy_dump(), snapshot).input_sha256 == proof.input_sha256
    with pytest.raises(AgentTaskError):
        parse_android_input_evidence(live.replace(b"DispatchEnabled: true", b"DispatchEnabled: false")
            + b"\nInput Dispatcher State at time of last ANR:\n" + live, policy_dump(), snapshot)


def test_half_open_geometry_detects_even_an_isolated_missing_swipe_point():
    rects = (AndroidRect(0, 5, 5, 10), AndroidRect(5, 0, 10, 5))
    assert not covers_android_path(rects, (1, 9), (9, 1))
    assert covers_android_path((AndroidRect(0, 0, 10, 10),), (0, 0), (9, 9))
    assert not covers_android_path((AndroidRect(0, 0, 10, 10),), (0, 0), (10, 9))


@pytest.mark.parametrize("mutate", [
    lambda raw: raw.replace(b"PendingEvent: <none>", b"PendingEvent:\n    busy"),
    lambda raw: raw.replace(b"DispatchEnabled: true", b"DispatchEnabled: false"),
    lambda raw: raw.replace(b"frame=[0,0][100,200]", b"frame=[0,0][99,200]"),
])
def test_same_command_connection_refuses_changed_native_input_before_any_write(run_guard, tmp_path, snapshot, mutate):
    raw, policy = input_dump(), policy_dump()
    proof = parse_android_input_evidence(raw, policy, snapshot)
    (tmp_path / "input").write_bytes(mutate(raw))
    (tmp_path / "policy").write_bytes(policy)
    result = run_guard(input_evidence=proof)
    assert result.returncode == 95
    parsed = parse_android_action_result(AdbShellResult(result.stdout, result.stderr, result.returncode))
    assert parsed.phase == "pre_input_refused" and not parsed.may_have_effect
    assert not (tmp_path / "actions").exists()


def test_checked_command_preserves_dynamic_history_but_refuses_a_new_lock(run_guard, tmp_path, snapshot):
    raw, policy = input_dump(), policy_dump()
    proof = parse_android_input_evidence(raw, policy, snapshot)
    (tmp_path / "input").write_bytes(raw.replace(b"RecentQueue: <empty>", b"RecentQueue: length=1\n    old-event"))
    (tmp_path / "policy").write_bytes(policy)
    assert run_guard(input_evidence=proof).stdout == ACTION_MARKER
    (tmp_path / "actions").unlink()
    (tmp_path / "policy").write_bytes(policy.replace(b"mIsShowing=false", b"mIsShowing=true"))
    assert run_guard(input_evidence=proof).returncode == 95
    assert not (tmp_path / "actions").exists()


def test_sdk_checked_proposal_reads_security_without_dispatch_or_input_authority():
    class SafeServer(Server):
        def shell(self, transport, command, **kwargs):
            if command == IDENTITY_PROBE:
                return super().shell(transport, command, **kwargs)
            assert "/system/bin/dumpsys input" in command
            assert "/system/bin/input -d" not in command
            self.calls.append("input-proof")
            return AdbShellResult(INPUT_MARKER + input_dump() + POLICY_MARKER + policy_dump() + SAFETY_END, b"", 0)

    server = SafeServer()
    proposal = session(server).propose_checked("AC_android_tap", {"x": 10, "y": 20})
    assert proposal.input_authorized is False
    assert proposal.input_evidence.input_authorized is False
    assert server.calls == ["devices", (42, IDENTITY_PROBE), "input-proof"]


def test_native_security_probe_round_trips_through_actual_shell_without_any_input(run_guard, tmp_path):
    (tmp_path / "input").write_bytes(input_dump())
    (tmp_path / "policy").write_bytes(policy_dump())
    result = run_guard(probe="input")
    assert result.returncode == 0
    assert result.stdout == INPUT_MARKER + input_dump() + POLICY_MARKER + policy_dump() + SAFETY_END
    assert not (tmp_path / "actions").exists()


def test_invisible_and_nonintercepting_transparent_windows_are_not_false_occlusions(snapshot):
    for flags in ("NOT_VISIBLE", "NOT_TOUCHABLE"):
        before = input_record(0, name="foreign", flags=flags, alpha="0.00")
        proof = parse_android_input_evidence(input_dump(before, input_record(1)), policy_dump(), snapshot)
        proof.require_path((5, 5), (6, 6))
    intercepting = input_record(0, name="foreign", alpha="0.00")
    proof = parse_android_input_evidence(input_dump(intercepting, input_record(1)), policy_dump(), snapshot)
    with pytest.raises(AgentTaskError, match="foreign"):
        proof.require_path((5, 5), (6, 6))


def test_global_monitors_remain_explicit_unapproved_metadata(snapshot):
    raw = input_dump().replace(b"  Global Monitors: <none>", b"  Global monitors on display 0:\n    0: 'system-monitor', ")
    proof = parse_android_input_evidence(raw, policy_dump(), snapshot)
    assert proof.has_global_monitors is True
    assert proof.input_authorized is False
    assert "system-monitor" not in repr(proof)


def test_native_connection_cannot_claim_a_window_with_a_different_channel_name(snapshot):
    with pytest.raises(AgentTaskError):
        parse_android_input_evidence(input_dump().replace(b"channelName='abc123 org.example.app/.MainActivity (server)'",
            b"channelName='forged-other-channel'"),
                                     policy_dump(), snapshot)


@pytest.mark.parametrize("bad", [
    lambda raw: raw + b"Input Dispatcher State:\n", lambda raw: raw.replace(b"    42:", b"    bad-descriptor:"),
    lambda raw: raw.replace(b"  Connections:", b"  Connections: <none>"),
    lambda raw: raw.replace(b"    displayId=0, name='abc123", b"    displayId=1, name='abc123"),
    lambda raw: raw.replace(b"    Windows:", b"    Windows: <none>"),
    lambda raw: raw.replace(b"        transform (ROT_0) (IDENTITY)\n  Global", b"  Global"),
])
def test_unparsed_duplicate_or_wrong_display_evidence_never_certifies_input(snapshot, bad):
    with pytest.raises(AgentTaskError):
        parse_android_input_evidence(bad(input_dump()), policy_dump(), snapshot)
