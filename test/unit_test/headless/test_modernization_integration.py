"""The features of the platform / sync / mobile round, joined end to end -- on fakes.

Each feature has its own tests. These three cross the seams between them,
because that is where a set of individually green features can still not add
up to a workflow:

* a run journalled on one device becomes a candidate script that dry-runs, and
  then replays, on another;
* a config sync survives the server's store being reopened, through the same
  functions the Config Sync tab calls;
* a capability report says where each of its statements comes from.

Everything here runs against a fake ``adb`` host, an in-memory wire over a real
SQLite store, and desktops described through ``BackendContext``. That is
evidence about how the pieces fit. It is not evidence about a phone, a
compositor or a network, and the last test holds the reports to saying so.
"""
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest

import je_auto_control as ac
from je_auto_control.linux_wayland.authorisation import (
    INPUT, AuthorisationLedger, AuthorisationState,
)
from je_auto_control.utils.config_sync import (
    ConfigBucket, ConfigSyncClient, ConfigSyncConflict, ConfigSyncError,
    RevisionConflictError, session as sync_session,
)

from headless._mobile_doubles import FakeAdbHost

_USER = "alice"
_SERVER = "https://sync.invalid"

_RUN = [
    ["AC_android_tap", {"x": 10, "y": 20}],
    ["AC_loop", {"times": 2, "body": [
        ["AC_android_swipe", {"x1": 1, "y1": 2, "x2": 3, "y2": 4}]]}],
    ["AC_android_type_text", {"text": "hello"}],
]


@pytest.fixture
def adb_host(monkeypatch):
    """Two pretend Android devices behind the real ``AdbClient``."""
    host = FakeAdbHost()
    host.add("recorded-on")
    host.add("replayed-on")
    monkeypatch.setattr("je_auto_control.android.adb_client.subprocess.run", host.run)
    monkeypatch.setattr("je_auto_control.android.adb_client.shutil.which", lambda _name: "adb")
    return host


@pytest.fixture(autouse=True)
def _no_journal_left_running():
    yield
    ac.stop_action_journal()


# --- journal -> candidate script -> device --------------------------------

@dataclass
class ReplayReport:
    """What running a candidate did, in the terms its manifest uses."""

    source_steps: List[str] = field(default_factory=list)
    device_effects: List[str] = field(default_factory=list)


def _replay(actions: List[Any], host: FakeAdbHost, serial: str, *, dry_run: bool) -> ReplayReport:
    report = ReplayReport()
    before = len(host.devices[serial].input_calls)
    with ac.open_device(ac.DeviceContext("android", serial)) as session, ac.use_device(session):
        ac.executor.execute_action(
            actions, dry_run=dry_run, raise_on_error=True,
            step_callback=lambda action: report.source_steps.append(action[0]))
    report.device_effects = host.devices[serial].input_calls[before:]
    return report


def test_journal_to_script_to_device_result(adb_host, tmp_path):
    journal = tmp_path / "run.jsonl"
    with ac.open_device(ac.DeviceContext("android", "recorded-on")) as session, \
            ac.use_device(session):
        ac.start_action_journal(journal, run_id="checkout", session=session.device_id)
        try:
            ac.executor.execute_action(_RUN, raise_on_error=True)
        finally:
            stopped = ac.stop_action_journal()
    recorded = list(adb_host.devices["recorded-on"].input_calls)
    assert stopped["events"] == 5
    assert len(recorded) == 4  # the loop body ran twice

    candidate = ac.generate_candidate_from_log(journal, run_id="checkout")
    manifest = candidate.manifest
    assert manifest["executed"] is False
    assert manifest["outcomes_used_as_input"] is False
    assert candidate.observed_path_only is False
    assert candidate.actions == _RUN
    assert {event.session for event in ac.read_events(journal, run_id="checkout")} == {
        "recorded-on"}
    compile(candidate.code, "candidate.py", "exec")
    manifest_source_steps = [step["command"] for step in manifest["steps"] if step["emitted"]]

    # A dry run on the second device resolves every step and sends it nothing.
    dry = _replay(candidate.actions, adb_host, "replayed-on", dry_run=True)
    assert dry.source_steps == manifest_source_steps
    assert dry.device_effects == []

    # Run for real -- still a fake device -- it sends what the first one received.
    replay_report = _replay(candidate.actions, adb_host, "replayed-on", dry_run=False)
    assert replay_report.source_steps == manifest_source_steps
    assert replay_report.device_effects == recorded
    # Generating and replaying never reached back to the device it was recorded on.
    assert adb_host.devices["recorded-on"].input_calls == recorded


def test_each_run_of_a_shared_journal_becomes_its_own_candidate(adb_host, tmp_path):
    """One journal file holds many runs; a candidate is built from exactly one of them."""
    journal = tmp_path / "run.jsonl"
    with ac.open_device(ac.DeviceContext("android", "recorded-on")) as session, \
            ac.use_device(session):
        ac.start_action_journal(journal, run_id="first")
        ac.executor.execute_action(_RUN[:1], raise_on_error=True)
        ac.stop_action_journal()
        ac.start_action_journal(journal, run_id="second")
        ac.executor.execute_action(_RUN[2:], raise_on_error=True)
        ac.stop_action_journal()
    assert [run["run_id"] for run in ac.list_journal_runs(journal)] == ["first", "second"]
    assert ac.generate_candidate_from_log(journal, run_id="first").actions == _RUN[:1]
    assert ac.generate_candidate_from_log(journal, run_id="second").actions == _RUN[2:]


# --- config sync through a store restart ----------------------------------

class _Wire:
    """``ConfigSyncClient._request`` answered from a ``ConfigStore`` on disk.

    A new store object is built for every request, which is what a restarted
    server amounts to: nothing is carried in memory between two requests.
    """

    def __init__(self, store_path: Any) -> None:
        self.store_path = store_path
        self.requests: List[str] = []
        self.offline = False

    def request(self, client: ConfigSyncClient, method: str,
                body: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        self.requests.append(method)
        if self.offline:
            raise ConfigSyncError(f"config sync {method} failed: connection refused")
        store = ac.ConfigStore(self.store_path)
        if method == "GET":
            bucket = store.get(client.user_id)
            return None if bucket is None else {**bucket.to_dict(), "version": 2}
        assert body is not None, "the client must send a v2 envelope"
        assert body["version"] == 2, "the client must send a v2 envelope"
        try:
            revision = store.commit(
                client.user_id, ConfigBucket.from_dict(body["bucket"]),
                base_revision=body["base_revision"], operation_id=body["operation_id"])
        except RevisionConflictError as conflict:
            raise ConfigSyncConflict("behind", conflict.current_revision) from conflict
        return {"ok": True, "revision": revision, "version": 2}


@pytest.fixture
def wire(tmp_path, monkeypatch):
    endpoint = _Wire(tmp_path / "server" / "config_sync.sqlite3")
    monkeypatch.setattr(
        ConfigSyncClient, "_request",
        lambda client, method, body=None: endpoint.request(client, method, body))
    monkeypatch.delenv("AC_SIGNALING_SECRET", raising=False)
    return endpoint


def _machine(tmp_path, name: str) -> Dict[str, Any]:
    scripts = tmp_path / name / "scripts"
    scripts.mkdir(parents=True)
    return {"device_id": name, "sections": "scripts", "scripts_dir": str(scripts),
            "outbox_path": str(tmp_path / name / "outbox.sqlite3")}


def test_sync_restart_and_gui_session(wire, tmp_path):
    laptop, desktop = _machine(tmp_path, "laptop"), _machine(tmp_path, "desktop")
    script = [["AC_set_var", {"name": "user", "value": "alice"}]]
    (tmp_path / "laptop" / "scripts" / "login.json").write_text(json.dumps(script), "utf-8")

    first = sync_session.config_sync_run(_SERVER, _USER, **laptop)
    assert first["state"] == "synced"
    assert first["pending"] == 0
    committed_revision = ac.ConfigStore(wire.store_path).revision(_USER)
    assert committed_revision >= 1

    # The "restart": a store object that has never seen the file, and a status
    # read that touches no network at all.
    reopened_store = ac.ConfigStore(wire.store_path)
    assert reopened_store.revision(_USER) == committed_revision
    requests_before = len(wire.requests)
    reopened_sync = sync_session.config_sync_status(_SERVER, _USER, laptop["outbox_path"])
    assert len(wire.requests) == requests_before
    assert reopened_sync["revision"] == committed_revision
    assert reopened_sync["state"] == "synced"
    assert reopened_sync["pending"] == 0

    # The other machine gets the script from the reopened store.
    second = sync_session.config_sync_run(_SERVER, _USER, **desktop)
    assert second["state"] == "synced"
    arrived = tmp_path / "desktop" / "scripts" / "login.json"
    assert json.loads(arrived.read_text("utf-8")) == script

    # Offline: the change is queued on disk and survives until the server is back.
    wire.offline = True
    (tmp_path / "laptop" / "scripts" / "report.json").write_text("[]", "utf-8")
    offline = sync_session.config_sync_run(_SERVER, _USER, **laptop)
    assert offline["state"] == "offline"
    assert offline["pending"] == 1
    assert sync_session.config_sync_status(_SERVER, _USER, laptop["outbox_path"])["pending"] == 1
    wire.offline = False
    back = sync_session.config_sync_run(_SERVER, _USER, wait=True, **laptop)
    assert back["state"] == "synced"
    assert back["pending"] == 0
    assert ac.ConfigStore(wire.store_path).revision(_USER) > committed_revision


def test_the_config_sync_tab_calls_these_same_functions():
    """What this file drives is what the GUI drives -- not a parallel path."""
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from je_auto_control.gui import config_sync_tab
    assert config_sync_tab.session is sync_session
    source = open(config_sync_tab.__file__, encoding="utf-8").read()
    for name in ("config_sync_run", "config_sync_status", "config_sync_resolve",
                 "config_sync_full_resync"):
        assert f"session.{name}(" in source
        assert getattr(ac, name) is getattr(sync_session, name)


# --- a capability report that states its evidence -------------------------

_WAYLAND = {"XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": "wayland-0",
            "XDG_RUNTIME_DIR": "/run/user/1000"}


def _desktop(platform: str, environ: Optional[Dict[str, str]] = None, *, tools: tuple = (),
             libei: bool = False, ledger: Optional[AuthorisationLedger] = None,
             ) -> ac.BackendContext:
    return ac.BackendContext(
        platform=platform, environ=environ or {},
        which=lambda name: f"/usr/bin/{name}" if name in tools else None,
        library_present=lambda name: libei and name in ("ei", "oeffis"),
        session_bus_present=lambda: True, readable=lambda _path: True,
        compositor=lambda _environ: "8:1:1",
        authorisations=ledger if ledger is not None else AuthorisationLedger(),
        # Nothing read: a described Windows or macOS desktop is not this machine's.
        windows_facts=ac.WindowsFacts, mac_facts=ac.MacFacts,
        backend_version=lambda _backend: "")


def _desktop_evidence(capability: ac.Capability, platform: str) -> Dict[str, Any]:
    """Where one desktop capability's state comes from."""
    if platform.startswith("linux"):
        return {"kind": "probed", "reason": "read from the environment, PATH, the loader and "
                                            "the authorisation ledger; no event was sent"}
    reason = capability.detail or "the backend has no authorisation to report"
    return {"kind": "skipped", "reason": reason}


def desktop_report(context: ac.BackendContext) -> Dict[str, Any]:
    """A capability report for one described desktop, with its evidence."""
    snapshot = ac.probe_capabilities(context)
    return {
        "platform": snapshot.platform, "backend": snapshot.display_server,
        # A described desktop is not this machine: its backend reports no version.
        "version": snapshot.backend_version or None,
        "version_reason": "a described desktop's backend version cannot be read from here",
        "transport": "described", "hardware_verified": False,
        "capabilities": [{
            "name": capability.name, "state": capability.state.value,
            "backend": capability.backend, "usable": capability.usable,
            "recovery": capability.recovery,
            "evidence": _desktop_evidence(capability, snapshot.platform),
        } for capability in snapshot.capabilities],
    }


def device_report(session: ac.DeviceSession) -> Dict[str, Any]:
    """A capability report for one device session, with its evidence."""
    setup = ac.device_setup_report(session)
    return {
        "platform": setup.platform, "backend": setup.backend,
        "version": setup.backend_version, "os_version": setup.os_version,
        "transport": "fake", "hardware_verified": False,
        "capabilities": [{
            "name": name, "state": capability.state, "backend": setup.backend,
            "usable": capability.available, "recovery": capability.reason,
            "evidence": ({"kind": "probed", "reason": "reported by the session's setup probe"}
                         if capability.available else
                         {"kind": "skipped", "reason": capability.reason}),
        } for name, capability in setup.capabilities.items()],
    }


def _problems(report: Dict[str, Any]) -> List[str]:
    """Everything a report states without saying how it knows."""
    label = f"{report['platform']}/{report['backend']}"
    problems = []
    if not report["platform"] or not report["backend"]:
        problems.append(f"{label}: no platform or backend")
    if not report["version"] and not report.get("version_reason"):
        problems.append(f"{label}: no version and no reason for its absence")
    if report["hardware_verified"]:
        problems.append(f"{label}: claims hardware verification from a {report['transport']} run")
    for capability in report["capabilities"]:
        evidence = capability["evidence"]
        where = f"{label}: {capability['name']}"
        if evidence["kind"] not in ("probed", "skipped") or not evidence["reason"]:
            problems.append(f"{where} has no evidence")
        if not capability["backend"]:
            problems.append(f"{where} names no backend")
        if not capability["usable"] and not capability["recovery"] and evidence["kind"] == "probed":
            problems.append(f"{where} is unusable and says neither why nor what to do")
    return problems


def test_platform_capability_report_has_evidence(adb_host):
    refused = AuthorisationLedger()
    refused.transition(INPUT, AuthorisationState.DECLINED, "the user dismissed the dialog")
    reports = [
        desktop_report(_desktop("win32")),
        desktop_report(_desktop("darwin")),
        desktop_report(_desktop("linux", {"DISPLAY": ":0"})),
        desktop_report(_desktop("linux", _WAYLAND, tools=("grim",), libei=True)),
        desktop_report(_desktop("linux", _WAYLAND, tools=("grim", "ydotool"), libei=True,
                                ledger=refused)),
        desktop_report(_desktop("linux", _WAYLAND)),          # nothing installed at all
    ]
    adb_host.add("locked", state="unauthorized")
    for serial in ("recorded-on", "locked"):
        with ac.open_device(ac.DeviceContext("android", serial)) as session:
            before = list(adb_host.devices[serial].input_calls)
            reports.append(device_report(session))
            assert adb_host.devices[serial].input_calls == before    # a report sends no input

    problems = [problem for report in reports for problem in _problems(report)]
    all_verified_capabilities_have_evidence = problems == []
    assert all_verified_capabilities_have_evidence is True, problems

    by_platform = {(report["platform"], report["transport"]): report for report in reports}
    # Windows and macOS: reported, and labelled as not probed.
    for platform in ("win32", "darwin"):
        kinds = {item["evidence"]["kind"] for item in by_platform[(platform, "described")][
            "capabilities"]}
        assert kinds == {"skipped"}
    assert {item["state"] for item in reports[1]["capabilities"]} == {"unknown"}
    # A refused consent is a state with a way out, and ydotool being installed changes nothing.
    declined = next(item for item in reports[4]["capabilities"] if item["name"] == "input")
    assert (declined["state"], declined["backend"], declined["usable"]) == (
        "needs_permission", "libei", False)
    assert "reset_input_authorisation" in declined["recovery"]
    # The device reports carry what answered, and the locked one says what to fix.
    ready, locked = reports[-2], reports[-1]
    assert ready["backend"] == "adb"
    assert ready["version"].startswith("1.0.41")
    assert ready["os_version"] == "14"
    assert {item["state"] for item in locked["capabilities"]} == {"needs_permission"}
    assert all(item["evidence"]["kind"] == "skipped" for item in locked["capabilities"])
    # Nothing in this file touched hardware, and no report says otherwise.
    assert not any(report["hardware_verified"] for report in reports)
    json.dumps(reports)                                       # a report is plain data


def test_a_report_without_evidence_is_caught():
    """The checker above is only worth something if it fails on a bare claim."""
    report = desktop_report(_desktop("linux", _WAYLAND))
    report["capabilities"][0]["evidence"] = {"kind": "probed", "reason": ""}
    report["hardware_verified"] = True
    found = _problems(report)
    assert any("no evidence" in problem for problem in found)
    assert any("claims hardware verification" in problem for problem in found)
