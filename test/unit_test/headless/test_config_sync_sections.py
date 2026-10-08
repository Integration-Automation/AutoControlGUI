"""Which sections a sync covers is stated, not implied.

``config_sync_run(url, user, scripts_dir=...)`` syncs the scripts -- and this
machine's hotkeys, triggers and address book, because those three are the
default and the path only *adds* a section. Nothing in the report said so.
The default is kept (the GUI tab has a scripts folder and no section picker,
and hotkeys need that folder to make their script paths portable), but the
report now names the sections, and choosing them is validated.
"""
from unittest.mock import patch

import pytest

from je_auto_control.utils.config_sync import (
    ConfigSyncClient, ConfigSyncConflict, ConfigSyncError, config_sync_run, config_sync_status,
    default_adapters,
)
from je_auto_control.utils.config_sync.session import (
    DEFAULT_SECTIONS, SYNCABLE_SECTIONS, resolve_sections,
)

_URL = "https://sync.invalid"


class _Server:
    def __init__(self):
        self.body = None
        self.revision = 0

    def request(self, method, body=None):
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


def test_the_default_is_the_three_machine_stores_plus_what_a_path_enables():
    assert DEFAULT_SECTIONS == ("hotkeys", "triggers", "address_book")
    assert resolve_sections(None) == ["hotkeys", "triggers", "address_book"]
    assert resolve_sections(None, scripts_dir="s") == [
        "hotkeys", "triggers", "address_book", "scripts"]
    assert resolve_sections(None, scripts_dir="s", locators_path="l") == [
        "hotkeys", "triggers", "address_book", "scripts", "locators"]
    assert set(SYNCABLE_SECTIONS) == {"hotkeys", "triggers", "address_book", "scripts", "locators"}


def test_naming_sections_syncs_exactly_those():
    assert resolve_sections("scripts", scripts_dir="s") == ["scripts"]
    assert resolve_sections(["scripts", "hotkeys"], scripts_dir="s") == ["scripts", "hotkeys"]
    assert resolve_sections(" scripts , hotkeys ", scripts_dir="s") == ["scripts", "hotkeys"]
    # Naming one twice does not build two adapters fighting over one section.
    assert resolve_sections(["scripts", "scripts"], scripts_dir="s") == ["scripts"]


@pytest.mark.parametrize("sections", [[], (), ",", " , "])
def test_an_explicitly_empty_choice_is_an_error_not_everything(sections):
    with pytest.raises(ConfigSyncError, match="names no section"):
        resolve_sections(sections, scripts_dir="s")


def test_an_unknown_section_or_a_missing_store_is_refused_with_the_choices():
    with pytest.raises(ConfigSyncError, match="hotkeys, triggers, address_book, scripts, locators"):
        resolve_sections(["hotkey"])
    with pytest.raises(ConfigSyncError, match="scripts_dir"):
        resolve_sections(["scripts"])
    with pytest.raises(ConfigSyncError, match="locators_path"):
        resolve_sections("locators", scripts_dir="s")
    with pytest.raises(ConfigSyncError):
        resolve_sections([7])


def test_scripts_only_touches_only_the_scripts_section(tmp_path, server):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "a.json").write_text("[]", encoding="utf-8")
    report = config_sync_run(_URL, "alice", device_id="laptop", sections="scripts",
                             scripts_dir=str(scripts), outbox_path=str(tmp_path / "o.sqlite3"))
    assert report["sections"] == ["scripts"]
    assert set(server.body["sections"]) == {"scripts"}
    assert set(report["applied"]) == {"scripts"}
    status = config_sync_status(_URL, "alice", str(tmp_path / "o.sqlite3"))
    assert status["sections"] == ["scripts"], "the status says what the last run covered"


def test_the_report_names_the_sections_the_default_covered(tmp_path, server, monkeypatch):
    built = []

    def fake_adapters(device_id, **options):
        built.append(options)
        return default_adapters(device_id, sections=["scripts"], scripts_dir=options["scripts_dir"])

    scripts = tmp_path / "scripts"
    scripts.mkdir()
    # The real default would read this machine's hotkey daemon and address book.
    monkeypatch.setattr("je_auto_control.utils.config_sync.session.default_adapters", fake_adapters)
    config_sync_run(_URL, "alice", device_id="laptop", scripts_dir=str(scripts),
                    outbox_path=str(tmp_path / "o.sqlite3"))
    assert built[0]["sections"] is None, "no sections given means the documented default"


def test_default_adapters_builds_one_adapter_per_resolved_section(tmp_path):
    adapters = default_adapters("laptop", sections=["scripts"], scripts_dir=str(tmp_path))
    assert [adapter.section for adapter in adapters] == ["scripts"]


def test_the_mcp_schema_lists_the_sections():
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    tools = {tool.name: tool
             for tool in build_default_tool_registry(read_only=False, aliases=False)}
    run = tools["ac_config_sync_run"]
    assert set(run.input_schema["properties"]["sections"]["items"]["enum"]) == set(
        SYNCABLE_SECTIONS)
    assert "sections" in run.description and "address book" in run.description
