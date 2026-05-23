"""Phase 3.1: host_service installer output tests."""
import json

import pytest

# These imports go through host_service which lazy-imports aiortc.
# Skip if WebRTC extras are missing — install commands themselves work
# without aiortc, but the module-level pull-through fails without it.
pytest.importorskip("aiortc")
pytest.importorskip("av")

from je_auto_control.utils.remote_desktop import host_service  # noqa: E402


def test_write_default_config_creates_stub(tmp_path):
    target = tmp_path / "service.json"
    host_service.write_default_config(target)
    assert target.exists()
    raw = json.loads(target.read_text(encoding="utf-8"))
    assert raw["token"] == "CHANGE_ME_BEFORE_USE"  # nosec B105  # test fixture
    assert "server_url" in raw and "host_id" in raw


def test_generate_systemd_unit(tmp_path):
    config = tmp_path / "service.json"
    host_service.write_default_config(config)
    output = tmp_path / "rd-host.service"
    host_service._generate_systemd_unit(config, output)
    text = output.read_text(encoding="utf-8")
    assert "[Service]" in text
    assert "ExecStart=" in text
    assert str(config) in text
    assert "Restart=on-failure" in text


def test_generate_launchd_plist(tmp_path):
    config = tmp_path / "service.json"
    host_service.write_default_config(config)
    output = tmp_path / "rd-host.plist"
    host_service._generate_launchd_plist(config, output)
    text = output.read_text(encoding="utf-8")
    assert "<key>Label</key>" in text
    assert "<key>RunAtLoad</key>" in text
    assert str(config) in text


def test_uninstall_systemd_removes_file(tmp_path):
    unit = tmp_path / "rd-host.service"
    unit.write_text("[Unit]\nDescription=stub\n", encoding="utf-8")
    rc = host_service._uninstall_systemd_unit(unit)
    assert rc == 0
    assert not unit.exists()


def test_uninstall_launchd_removes_file(tmp_path):
    plist = tmp_path / "rd-host.plist"
    plist.write_text("<plist/>", encoding="utf-8")
    rc = host_service._uninstall_launchd_plist(plist)
    assert rc == 0
    assert not plist.exists()


def test_uninstall_returns_error_for_missing_unit(tmp_path):
    nonexistent = tmp_path / "nope.service"
    assert host_service._uninstall_systemd_unit(nonexistent) == 1


def test_arg_parser_includes_uninstall_commands():
    parser = host_service._build_arg_parser()
    # argparse stores subparser names in choices on the dest action.
    sub_action = next(
        a for a in parser._actions if a.dest == "command"
    )
    choices = set(sub_action.choices.keys())
    assert "uninstall-windows-service" in choices
    assert "uninstall-launchd" in choices
    assert "uninstall-systemd" in choices
