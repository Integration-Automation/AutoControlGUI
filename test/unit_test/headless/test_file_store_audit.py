"""Regression tests for the file-store defects of the 2026-09-23 plugin/loader audit.

Two skill libraries or element repositories on one file dropped each other's
saves; an asset set without ``db`` was gone by the next command, and an
unreadable value was stored and failed every later read; a config-bundle
entry without content overwrote its file with ``null`` and imported files
kept the umask's permissions; agent memory never matched non-ASCII words;
string tags were split into letters; action files with a BOM or in a legacy
encoding failed with a raw error.
"""
import json
import os
import stat
import sys

import pytest

from je_auto_control.utils.agent_memory.agent_memory import AgentMemory
from je_auto_control.utils.assets import assets
from je_auto_control.utils.config_bundle.config_bundle import import_config_bundle
from je_auto_control.utils.element_repository.element_repository import ElementRepository
from je_auto_control.utils.exception.exceptions import AutoControlJsonActionException
from je_auto_control.utils.json.json_file import read_action_json
from je_auto_control.utils.skill_library.skill_library import SkillLibrary

LOGIN = "登入"   # a non-ASCII word; [a-z0-9] tokens never matched it


def test_two_skill_libraries_keep_each_others_saves(tmp_path):
    path = str(tmp_path / "skills.json")
    first, second = SkillLibrary(path), SkillLibrary(path)
    first.save("login", [["AC_x"]])
    second.save("logout", [["AC_y"]])
    assert SkillLibrary(path).names() == ["login", "logout"]


def test_two_element_repositories_keep_each_others_saves(tmp_path):
    path = str(tmp_path / "elements.json")
    first, second = ElementRepository(path), ElementRepository(path)
    first.save("ok", name="OK")
    second.save("cancel", name="Cancel")
    assert ElementRepository(path).keys() == ["cancel", "ok"]


@pytest.mark.parametrize("factory", [SkillLibrary, ElementRepository])
def test_a_corrupt_store_raises_instead_of_being_erased(tmp_path, factory):
    path = tmp_path / "store.json"
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError):
        factory(str(path))
    assert path.read_text(encoding="utf-8") == "not json"


def test_a_string_tag_is_one_tag(tmp_path):
    skill = SkillLibrary(str(tmp_path / "s.json")).save("s", [["AC_x"]], tags="login")
    assert skill.tags == ["login"]


def test_an_asset_without_db_survives_to_the_next_command():
    assets.store_set("audit_url", "http://a")
    assert assets.store_get("audit_url")["value"] == "http://a"


@pytest.mark.parametrize("value, asset_type", [("eighty", "int"), ("x", "integer")])
def test_an_unreadable_asset_is_refused_when_set(value, asset_type):
    with pytest.raises(ValueError):
        assets.AssetStore(None).set("port", value, asset_type=asset_type)


def _bundle(entry):
    return {"manifest": {"version": 1}, "files": {"admin_hosts.json": entry}}


def test_a_bundle_entry_without_content_is_refused(tmp_path):
    target = tmp_path / "admin_hosts.json"
    target.write_text('{"hosts": []}', encoding="utf-8")
    report = import_config_bundle(_bundle({"format": "json"}), root=tmp_path)
    assert report.skipped == ["admin_hosts.json"] and report.written == []
    assert json.loads(target.read_text(encoding="utf-8")) == {"hosts": []}


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_imported_files_are_private(tmp_path):
    import_config_bundle(_bundle({"format": "json", "content": {"hosts": []}}), root=tmp_path)
    mode = stat.S_IMODE(os.stat(tmp_path / "admin_hosts.json").st_mode)
    assert mode == 0o600


def test_agent_memory_recalls_non_ascii_words(tmp_path):
    memory = AgentMemory(str(tmp_path / "m.db"))
    memory.remember(f"{LOGIN} ERP", steps=[["AC_x"]], outcome="ok")
    assert [episode.goal for episode in memory.recall(LOGIN)] == [f"{LOGIN} ERP"]


def test_agent_memory_keeps_a_string_tag_whole(tmp_path):
    memory = AgentMemory(str(tmp_path / "m.db"))
    memory.remember("goal", steps=[["AC_x"]], tags="login")
    assert memory.recent(limit=1)[0].tags == ["login"]


def test_an_action_file_with_a_bom_is_read(tmp_path):
    path = tmp_path / "flow.json"
    path.write_bytes(b"\xef\xbb\xbf" + b'[["AC_x"]]')
    assert read_action_json(str(path)) == [["AC_x"]]


def test_an_action_file_that_is_not_utf8_raises_the_module_error(tmp_path):
    path = tmp_path / "flow.json"
    path.write_bytes('[["AC_x", {"t": "café"}]]'.encode("cp1252"))
    with pytest.raises(AutoControlJsonActionException):
        read_action_json(str(path))
