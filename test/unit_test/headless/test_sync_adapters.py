"""Config-sync adapters: what leaves this machine, and what arriving data may do.

Syncing settings between machines must not carry secrets or machine paths,
must not arm a hotkey or trigger on the machine that receives it, and must
not leave a script without the content its hash promises. The folder mirror
and the clipboard channel must not send back what they just received.
"""
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from je_auto_control.utils.config_sync import (
    ConfigSyncClient, ConfigSyncConflict, ConfigSyncError, SyncOutbox,
)
from je_auto_control.utils.config_sync.adapters import (
    AddressBookSyncAdapter, HotkeySyncAdapter, LocatorSyncAdapter, ScriptSyncAdapter,
    SyncAdapter, TriggerSyncAdapter, is_local_ref,
)
from je_auto_control.utils.config_sync.assets import (
    AssetManifest, AssetSyncError, DirectoryAssetTransport, publish_assets, sync_assets,
)
from je_auto_control.utils.config_sync.session import (
    config_sync_status, default_device_id, resolve_conflict, run_full_resync, run_sync,
    sync_status,
)
from je_auto_control.utils.hotkey.hotkey_daemon import HotkeyDaemon
from je_auto_control.utils.remote_desktop.clipboard_sync import ClipboardEchoGuard
from je_auto_control.utils.remote_desktop.file_sync import FolderSyncEngine
from je_auto_control.utils.triggers.trigger_engine import (
    AllOfTrigger, CronTrigger, ImageAppearsTrigger, TriggerEngine,
)

_URL = "https://sync.invalid"


class _Server:
    """The revision-checked bucket endpoint, in memory."""

    def __init__(self):
        self.body = None
        self.revision = 0
        self.offline = False

    def request(self, method, body=None):
        if self.offline:
            raise ConfigSyncError("config sync: connection refused")
        if method == "GET":
            return self.body
        if body["base_revision"] != self.revision:
            raise ConfigSyncConflict("behind", self.revision)
        self.revision += 1
        self.body = {**body["bucket"], "revision": self.revision}
        return {"ok": True, "revision": self.revision}


@pytest.fixture
def server():
    endpoint = _Server()
    with patch.object(ConfigSyncClient, "_request",
                      new=lambda _client, method, body=None: endpoint.request(method, body)):
        yield endpoint


class _Machine:
    """One device: its own outbox, its own stores, the shared server."""

    def __init__(self, tmp_path, name):
        self.name = name
        self.home = tmp_path / name
        self.scripts = self.home / "scripts"
        self.scripts.mkdir(parents=True)
        self.outbox = SyncOutbox(self.home / "outbox.sqlite3", account="alice", endpoint=_URL,
                                 base_delay_s=0.0)
        self.client = ConfigSyncClient(_URL, user_id="alice")
        self.adapters = []

    def sync(self, **options):
        return run_sync(self.client, self.outbox, self.adapters, device_id=self.name, **options)


class _DictAdapter(SyncAdapter):
    """A section backed by a plain dict, for the rules every adapter shares."""

    section = "custom"
    path_fields = ("script_path",)

    def __init__(self, origin, store, scripts_dir=None):
        super().__init__(origin, scripts_dir=scripts_dir)
        self.store = store

    def read_local(self):
        return {key: dict(value) for key, value in self.store.items()}

    def write_local(self, key, value, existing):
        self.store[key] = dict(value)

    def delete_local(self, key):
        self.store.pop(key, None)


def _pair(tmp_path):
    return _Machine(tmp_path, "laptop"), _Machine(tmp_path, "desktop")


# --- scripts and assets ----------------------------------------------------

def test_script_asset_hash_round_trip(tmp_path, server):
    laptop, desktop = _pair(tmp_path)
    shared = tmp_path / "shared-assets"
    small = json.dumps([["AC_click_mouse", {"mouse_keycode": "mouse_left"}]]).encode("utf-8")
    large = json.dumps([["AC_write", {"write_string": "x" * 100_000}]]).encode("utf-8")
    (laptop.scripts / "sub").mkdir()
    (laptop.scripts / "small.json").write_bytes(small)
    (laptop.scripts / "sub" / "large.json").write_bytes(large)
    laptop.adapters = [ScriptSyncAdapter("laptop", laptop.scripts)]
    desktop.adapters = [ScriptSyncAdapter("desktop", desktop.scripts)]
    transport = DirectoryAssetTransport(shared)

    assert laptop.sync(asset_transport=transport).state == "synced"
    report = desktop.sync(asset_transport=transport)

    assert report.state == "synced"
    for name, source in (("small.json", small), ("sub/large.json", large)):
        source_hash = hashlib.sha256(source).hexdigest()
        received_hash = hashlib.sha256((desktop.scripts / name).read_bytes()).hexdigest()
        assert received_hash == source_hash
    # The large script went through the transport, not through the bucket.
    assert "content" not in server.body["sections"]["scripts"]["sub/large.json"]["value"]
    assert report.assets["received"]["transferred"] == ["sub/large.json"]
    # Nothing changed, so nothing is sent again -- and nothing was deleted.
    before = server.revision
    assert desktop.sync(asset_transport=transport).state == "synced"
    assert laptop.sync(asset_transport=transport).state == "synced"
    assert server.revision == before
    assert (laptop.scripts / "sub" / "large.json").read_bytes() == large


def test_a_large_script_without_its_content_is_not_mistaken_for_a_deletion(tmp_path, server):
    laptop, desktop = _pair(tmp_path)
    large = json.dumps([["AC_write", {"write_string": "x" * 100_000}]]).encode("utf-8")
    (laptop.scripts / "large.json").write_bytes(large)
    laptop.adapters = [ScriptSyncAdapter("laptop", laptop.scripts)]
    desktop.adapters = [ScriptSyncAdapter("desktop", desktop.scripts)]
    laptop.sync()

    report = desktop.sync()      # no transport: the content cannot arrive
    assert "large.json" in report.applied["scripts"]["skipped"]
    assert not (desktop.scripts / "large.json").exists()
    desktop.sync()
    laptop.sync()
    assert (laptop.scripts / "large.json").read_bytes() == large, "the laptop's copy survived"
    assert server.body["sections"]["scripts"]["large.json"]["deleted"] is False


def test_a_tampered_asset_is_refused_and_the_old_file_survives(tmp_path):
    root = tmp_path / "scripts"
    root.mkdir()
    (root / "template.png").write_bytes(b"old image")
    wanted = b"new image"
    manifest = AssetManifest.from_entries(root, {"template.png": {
        "sha256": hashlib.sha256(wanted).hexdigest(), "size": len(wanted)}})

    class _Tampering:
        def fetch(self, sha256):
            return b"evil bits"

    result = sync_assets(manifest, _Tampering())
    assert "template.png" in result.failed and result.transferred == []
    assert (root / "template.png").read_bytes() == b"old image"
    assert [path.name for path in root.iterdir()] == ["template.png"], "no temp file left"


def test_assets_publish_fetch_and_stay_inside_the_folder(tmp_path):
    source, target, shared = tmp_path / "a", tmp_path / "b", tmp_path / "shared"
    (source / "img").mkdir(parents=True)
    target.mkdir()
    (source / "img" / "ok.png").write_bytes(b"\x89PNG data")
    manifest = AssetManifest.from_directory(source, ("*.png",))
    transport = DirectoryAssetTransport(shared)
    assert publish_assets(manifest, transport).transferred == ["img/ok.png"]
    assert publish_assets(manifest, transport).unchanged == ["img/ok.png"]

    incoming = AssetManifest(root=target, assets=manifest.assets)
    assert sync_assets(incoming, transport).transferred == ["img/ok.png"]
    assert sync_assets(incoming, transport).unchanged == ["img/ok.png"]
    assert (target / "img" / "ok.png").read_bytes() == b"\x89PNG data"

    digest = manifest.assets[0].sha256
    for escaping in ("../outside.png", "/abs.png", "C:/abs.png", "a\\..\\b.png"):
        bad = AssetManifest.from_entries(target, {escaping: {"sha256": digest, "size": 9}})
        assert escaping in sync_assets(bad, transport).failed
    assert not (tmp_path / "outside.png").exists()
    with pytest.raises(AssetSyncError):
        AssetManifest.from_entries(target, {"x.png": {"sha256": "not-a-hash", "size": 1}})


def test_a_script_with_a_literal_secret_is_withheld(tmp_path, server):
    laptop, _desktop = _pair(tmp_path)
    (laptop.scripts / "login.json").write_text(json.dumps(
        [["AC_write", {"password": "hunter2-very-secret-value"}]]), encoding="utf-8")
    (laptop.scripts / "ok.json").write_text(json.dumps(
        [["AC_write", {"password": "${secrets.login}"}]]), encoding="utf-8")
    laptop.adapters = [ScriptSyncAdapter("laptop", laptop.scripts)]
    report = laptop.sync()
    assert "scripts/login.json" in report.withheld
    assert set(server.body["sections"]["scripts"]) == {"ok.json"}
    assert "hunter2" not in json.dumps(server.body)


# --- secrets and machine paths ---------------------------------------------

def test_secret_is_local(tmp_path, server):
    laptop, desktop = _pair(tmp_path)
    laptop_store = {"vpn": {"host": "10.0.0.1", "password": "laptop-pass-123",
                            "api_token": "${secrets.vpn_token}"}}
    desktop_store = {"vpn": {"host": "old", "password": "desktop-pass-456"}}
    laptop.adapters = [_DictAdapter("laptop", laptop_store)]
    desktop.adapters = [_DictAdapter("desktop", desktop_store)]

    laptop.sync()
    sent = server.body["sections"]["custom"]["vpn"]["value"]
    sync_payload_contains_secret = "laptop-pass-123" in json.dumps(server.body)
    assert sync_payload_contains_secret is False
    assert is_local_ref(sent["password"])
    assert sent["api_token"] == "${secrets.vpn_token}", "a reference is not a secret"

    # The desktop pushes its own older version of the same key: a conflict,
    # not a silent overwrite of either side.
    report = desktop.sync()
    assert report.state == "conflict" and report.conflicts == ["custom/vpn"]
    resolved = resolve_conflict(desktop.outbox, desktop.adapters, device_id="desktop",
                                section="custom", key="vpn", choice=_sibling(server, "laptop"))
    assert resolved["value"]["host"] == "10.0.0.1"
    assert desktop.sync().state == "synced"
    assert desktop_store["vpn"]["host"] == "10.0.0.1"
    assert desktop_store["vpn"]["password"] == "desktop-pass-456", "its own secret stayed"
    assert laptop.sync().state == "synced"
    assert laptop_store["vpn"]["password"] == "laptop-pass-123"


def _sibling(server, origin):
    siblings = server.body["sections"]["custom"]["vpn"]["siblings"]
    return [sibling["origin"] for sibling in siblings].index(origin)


def test_machine_paths_travel_as_references(tmp_path, server):
    laptop, desktop = _pair(tmp_path)
    outside = tmp_path / "elsewhere" / "private.json"
    laptop_store = {"in": {"script_path": str(laptop.scripts / "run.json")},
                    "out": {"script_path": str(outside)}}
    desktop_store = {}
    laptop.adapters = [_DictAdapter("laptop", laptop_store, laptop.scripts)]
    desktop.adapters = [_DictAdapter("desktop", desktop_store, desktop.scripts)]
    laptop.sync()
    assert str(tmp_path) not in json.dumps(server.body), "no absolute path left the machine"

    report = desktop.sync()
    assert Path(desktop_store["in"]["script_path"]) == desktop.scripts / "run.json"
    assert "out" in report.applied["custom"]["skipped"] and "out" not in desktop_store
    # Not having it here is not a deletion for the laptop.
    desktop.sync()
    laptop.sync()
    assert "out" in laptop_store


def test_a_reference_cannot_escape_the_scripts_folder(tmp_path):
    adapter = _DictAdapter("laptop", {}, tmp_path / "scripts")
    escaping = {"$local": "path", "root": "scripts", "relative": "../../etc/passwd"}
    with pytest.raises(ConfigSyncError):
        adapter.from_portable({"script_path": escaping}, None)
    for drive_or_backslash in ("C:/Windows/x.json", "a\\..\\..\\x.json"):
        with pytest.raises(ConfigSyncError):
            adapter.from_portable({"script_path": {
                "$local": "path", "root": "scripts", "relative": drive_or_backslash}}, None)
    good = hashlib.sha256(b"[]").hexdigest()
    for key in ("../evil.json", "/abs.json", "C:/abs.json", "a\\..\\..\\evil.json"):
        with pytest.raises(ConfigSyncError):
            ScriptSyncAdapter("laptop", tmp_path / "s").write_local(
                key, {"content": "[]", "sha256": good}, None)
    assert not (tmp_path / "evil.json").exists()
    with pytest.raises(ConfigSyncError):
        ScriptSyncAdapter("laptop", tmp_path).write_local(
            "ok.json", {"content": "[]", "sha256": "0" * 64}, None)


# --- hotkeys and triggers are never armed by a sync ------------------------

def test_sync_never_enables_trigger(tmp_path, server):
    laptop, desktop = _pair(tmp_path)
    ran = []
    source = TriggerEngine(executor=ran.append)
    target = TriggerEngine(executor=ran.append)
    source.add(ImageAppearsTrigger(trigger_id="img", script_path=str(laptop.scripts / "a.json"),
                                   image_path=str(laptop.scripts / "t.png"), enabled=True))
    source.add(CronTrigger(trigger_id="cron", script_path=str(laptop.scripts / "a.json"),
                           cron="0 9 * * *", enabled=True))
    source.add(AllOfTrigger(trigger_id="both", script_path=str(laptop.scripts / "a.json")))
    laptop.adapters = [TriggerSyncAdapter("laptop", source, scripts_dir=laptop.scripts)]
    desktop.adapters = [TriggerSyncAdapter("desktop", target, scripts_dir=desktop.scripts)]

    # Composites are synced too (test_sync_composite_triggers.py) -- and arrive disabled.
    assert laptop.sync().withheld == {}
    report = desktop.sync()

    received = {trigger.trigger_id: trigger for trigger in target.list_triggers()}
    assert set(received) == {"img", "cron", "both"}
    enabled_triggers = [trigger.trigger_id for trigger in received.values() if trigger.enabled]
    assert enabled_triggers == []
    assert sorted(report.applied["triggers"]["left_disabled"]) == ["both", "cron", "img"]
    assert Path(received["img"].image_path) == desktop.scripts / "t.png"
    assert received["cron"].cron == "0 9 * * *"
    assert not target.is_running and not source.is_running and ran == []
    assert "enabled" not in json.dumps(server.body["sections"]["triggers"])

    # The laptop edits its (enabled) trigger; the desktop's stays off.
    next(t for t in source.list_triggers() if t.trigger_id == "cron").cron = "30 9 * * *"
    laptop.sync()
    desktop.sync()
    cron = next(t for t in target.list_triggers() if t.trigger_id == "cron")
    assert cron.cron == "30 9 * * *" and cron.enabled is False
    # Once this machine's user enables it, a later sync leaves that alone too.
    target.set_enabled("cron", True)
    next(t for t in source.list_triggers() if t.trigger_id == "cron").cron = "45 9 * * *"
    laptop.sync()
    desktop.sync()
    cron = next(t for t in target.list_triggers() if t.trigger_id == "cron")
    assert cron.cron == "45 9 * * *" and cron.enabled is True
    assert next(t for t in source.list_triggers() if t.trigger_id == "img").enabled is True


def test_sync_never_enables_a_hotkey(tmp_path, server):
    laptop, desktop = _pair(tmp_path)
    source, target = HotkeyDaemon(), HotkeyDaemon()
    source.bind("ctrl+alt+k", str(laptop.scripts / "a.json"), binding_id="hk1")
    laptop.adapters = [HotkeySyncAdapter("laptop", source, scripts_dir=laptop.scripts)]
    desktop.adapters = [HotkeySyncAdapter("desktop", target, scripts_dir=desktop.scripts)]
    laptop.sync()
    report = desktop.sync()

    [binding] = target.list_bindings()
    assert binding.combo == "ctrl+alt+k" and binding.enabled is False
    assert Path(binding.script_path) == desktop.scripts / "a.json"
    assert report.applied["hotkeys"]["left_disabled"] == ["hk1"]
    assert not target.is_running
    assert source.list_bindings()[0].enabled is True, "the sender's own state is untouched"

    source.unbind("hk1")
    laptop.sync()
    desktop.sync()
    assert target.list_bindings() == []


def test_a_binding_this_platform_refuses_is_skipped_not_deleted_for_everyone(tmp_path, server):
    laptop, desktop = _pair(tmp_path)

    class _Picky(HotkeyDaemon):
        def bind(self, combo, script_path, binding_id=None, *, enabled=True):
            raise ValueError(f"cannot register {combo} here")

    source, target = HotkeyDaemon(), _Picky()
    source.bind("ctrl+alt+k", str(laptop.scripts / "a.json"), binding_id="hk1")
    laptop.adapters = [HotkeySyncAdapter("laptop", source, scripts_dir=laptop.scripts)]
    desktop.adapters = [HotkeySyncAdapter("desktop", target, scripts_dir=desktop.scripts)]
    laptop.sync()
    assert "hk1" in desktop.sync().applied["hotkeys"]["skipped"]
    desktop.sync()
    laptop.sync()
    assert [binding.binding_id for binding in source.list_bindings()] == ["hk1"]


# --- locators and the address book -----------------------------------------

def test_locators_and_address_book_round_trip(tmp_path, server):
    from je_auto_control.utils.element_repository import ElementRepository
    from je_auto_control.utils.remote_desktop.address_book import AddressBook
    laptop, desktop = _pair(tmp_path)
    repos = [ElementRepository(str(machine.home / "locators.json"))
             for machine in (laptop, desktop)]
    books = [AddressBook(machine.home / "address_book.json") for machine in (laptop, desktop)]
    repos[0].save("ok_button", name="OK", role="button")
    books[0].upsert(host_id="host1", server_url="https://rd.invalid", label="Office")
    books[0].set_tags(host_id="host1", server_url="https://rd.invalid", tags=["work"])
    books[0].toggle_favorite(host_id="host1", server_url="https://rd.invalid")
    laptop.adapters = [LocatorSyncAdapter("laptop", repos[0]),
                       AddressBookSyncAdapter("laptop", books[0])]
    desktop.adapters = [LocatorSyncAdapter("desktop", repos[1]),
                        AddressBookSyncAdapter("desktop", books[1])]
    laptop.sync()
    desktop.sync()

    assert repos[1].get("ok_button") == {"name": "OK", "role": "button"}
    [entry] = books[1].list_entries()
    assert (entry["label"], entry["tags"], entry["favorite"]) == ("Office", ["work"], True)
    assert "last_used" not in json.dumps(server.body["sections"]["address_book"])

    repos[1].remove("ok_button")
    books[1].remove(host_id="host1", server_url="https://rd.invalid")
    desktop.sync()
    laptop.sync()
    assert repos[0].all() == {} and books[0].list_entries() == []


# --- status, offline, resync -----------------------------------------------

def test_offline_changes_wait_in_the_outbox_and_the_status_says_so(tmp_path, server):
    laptop, _desktop = _pair(tmp_path)
    store = {"a": {"v": 1}}
    laptop.adapters = [_DictAdapter("laptop", store)]
    server.offline = True
    report = laptop.sync(max_attempts=2)
    assert (report.state, report.pending) == ("offline", 1) and report.error
    assert laptop.sync(max_attempts=1).pending == 1, "the same edit is not queued twice"
    status = sync_status(laptop.outbox)
    assert (status["state"], status["pending"], status["revision"]) == ("offline", 1, 0)

    server.offline = False
    report = laptop.sync()
    assert (report.state, report.pending, report.revision) == ("synced", 0, 1)
    status = config_sync_status(_URL, "alice", str(laptop.home / "outbox.sqlite3"))
    assert status["state"] == "synced" and status["last_success"] > 0


def test_a_cancelled_sync_stops_and_keeps_its_changes(tmp_path, server):
    import threading
    laptop, _desktop = _pair(tmp_path)
    laptop.adapters = [_DictAdapter("laptop", {"a": {"v": 1}})]
    cancel = threading.Event()
    cancel.set()
    report = laptop.sync(cancel=cancel)
    assert report.state == "cancelled" and report.pending == 1 and server.revision == 0


def test_a_retired_device_is_told_to_resync_and_adopts_the_server_state(tmp_path, server):
    laptop, desktop = _pair(tmp_path)
    # No hold, so the tombstone is really gone when the retired desktop returns:
    # the refusal is then all that keeps the entry from coming back.
    laptop.client = ConfigSyncClient(_URL, user_id="alice", tombstone_hold_s=0)
    laptop_store, desktop_store = {"a": {"v": 1}}, {}
    laptop.adapters = [_DictAdapter("laptop", laptop_store)]
    desktop.adapters = [_DictAdapter("desktop", desktop_store)]
    laptop.sync()
    desktop.sync()
    laptop.client.retire_peer("desktop")
    del laptop_store["a"]
    laptop.sync()
    laptop.sync()                      # the tombstone is collected: nobody waits for desktop
    assert server.body["sections"]["custom"] == {}

    desktop_store["a"] = {"v": "edited while away"}
    report = desktop.sync()
    assert report.state == "resync_required"
    assert server.body["sections"]["custom"] == {}, "the stale edit did not get in"

    report = run_full_resync(desktop.client, desktop.outbox, desktop.adapters,
                             device_id="desktop")
    assert report.state == "synced" and "custom/a" in report.withheld
    assert desktop_store == {}, "the deleted entry did not come back"
    assert desktop.sync().state == "synced"


def test_the_device_id_is_created_once_and_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    first = default_device_id()
    assert first and default_device_id() == first
    assert (tmp_path / ".je_auto_control" / "config_sync_device_id").read_text(
        encoding="utf-8").strip() == first


# --- the mirror channels do not echo ---------------------------------------

def test_clipboard_does_not_echo():
    host, viewer = ClipboardEchoGuard(), ClipboardEchoGuard()
    wire = []

    def copy_on(sender, receiver, text):
        """A local copy on one side, forwarded and applied on the other."""
        if sender.should_send("text", text):
            wire.append(text)
            receiver.note_remote("text", text)
            return True
        return False

    assert copy_on(viewer, host, "hello") is True
    # The host's watcher now sees "hello" on its clipboard: it must not go back.
    assert copy_on(host, viewer, "hello") is False
    # Nor does the viewer keep resending what the clipboard still holds.
    assert copy_on(viewer, host, "hello") is False
    assert wire == ["hello"]
    # A real change on the host does travel, once.
    assert copy_on(host, viewer, "reply") is True
    assert copy_on(viewer, host, "reply") is False
    assert wire == ["hello", "reply"]
    assert host.should_send("image", b"hello") is True, "another kind is other content"
    host.reset()
    assert host.should_send("text", "reply") is True, "after a reconnect nothing is assumed"


def test_a_folder_mirror_does_not_push_back_what_it_received(tmp_path):
    watch = tmp_path / "watch"
    watch.mkdir()
    sent = []
    # wait_until_stable=False: this is about echo, not about files still being written.
    engine = FolderSyncEngine(watch_dir=watch, sender=lambda _path, name: sent.append(name),
                              wait_until_stable=False)
    assert engine.poll_once() == []            # baseline

    # Noted before the bytes land, so a poll in between cannot echo it.
    incoming = b"from the peer"
    engine.note_received("report.txt", sha256=hashlib.sha256(incoming).hexdigest())
    (watch / "report.txt").write_bytes(incoming)
    (watch / "mine.txt").write_text("made here", encoding="utf-8")
    assert engine.poll_once() == ["mine.txt"]
    assert engine.poll_once() == [] and sent == ["mine.txt"]

    # Edited here afterwards: now it is a local change and goes out.
    (watch / "report.txt").write_bytes(b"edited locally")
    assert engine.poll_once() == ["report.txt"]


def test_a_received_file_noted_after_it_landed_is_not_echoed(tmp_path):
    watch = tmp_path / "watch"
    watch.mkdir()
    sent = []
    engine = FolderSyncEngine(watch_dir=watch, sender=lambda _path, name: sent.append(name))
    engine.poll_once()
    (watch / "a.bin").write_bytes(b"payload")
    engine.note_received("a.bin")
    assert engine.poll_once() == [] and sent == []


# --- the delivery surfaces: executor, MCP, Script Builder, facade ----------

_COMMANDS = ("AC_config_sync_run", "AC_config_sync_status", "AC_config_sync_resolve",
             "AC_config_sync_full_resync")


def test_the_commands_run_from_an_action_list(tmp_path, server):
    from je_auto_control.utils.executor.action_executor import executor
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "a.json").write_text("[]", encoding="utf-8")
    target = {"server_url": _URL, "user_id": "alice"}
    options = {"device_id": "laptop", "sections": "scripts", "scripts_dir": str(scripts),
               "outbox_path": str(tmp_path / "outbox.sqlite3")}
    record = executor.execute_action([
        ["AC_config_sync_run", {**target, **options}],
        ["AC_config_sync_status", {**target, "outbox_path": options["outbox_path"]}],
    ])
    run, status = list(record.values())
    assert run["state"] == "synced" and run["revision"] == 1
    assert status["state"] == "synced" and status["pending"] == 0
    assert set(server.body["sections"]["scripts"]) == {"a.json"}
    json.dumps(record)


def test_an_unknown_option_or_section_is_refused(tmp_path, server):
    from je_auto_control.utils.config_sync import config_sync_run
    options = {"device_id": "laptop", "outbox_path": str(tmp_path / "outbox.sqlite3")}
    with pytest.raises(ConfigSyncError, match="unknown config sync option"):
        config_sync_run(_URL, "alice", enable_everything=True, **options)
    with pytest.raises(ConfigSyncError, match="cannot sync section"):
        config_sync_run(_URL, "alice", sections=["scripts"], **options)
    assert server.revision == 0


def test_every_surface_knows_the_commands():
    import je_auto_control as ac
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    assert set(_COMMANDS) <= set(executor.known_commands())
    assert set(_COMMANDS) <= {spec.command for spec in _build_specs()}
    tools = {tool.name: tool
             for tool in build_default_tool_registry(read_only=False, aliases=False)}
    for command in _COMMANDS:
        assert "ac_" + command[3:] in tools
    assert tools["ac_config_sync_status"].annotations.read_only
    for acting in ("ac_config_sync_run", "ac_config_sync_resolve", "ac_config_sync_full_resync"):
        assert tools[acting].annotations.destructive and not tools[acting].annotations.read_only
    read_only = {tool.name
                 for tool in build_default_tool_registry(read_only=True, aliases=False)}
    assert "ac_config_sync_run" not in read_only and "ac_config_sync_status" in read_only
    for name in ("ConfigSyncClient", "SyncEntry", "SyncOutbox", "merge_entries", "sync_assets",
                 "config_sync_run", "SyncAdapter", "ConfigStore"):
        assert name in ac.__all__ and hasattr(ac, name)
