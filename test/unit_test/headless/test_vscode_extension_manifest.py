"""Tests for the AutoControl VS Code extension scaffold.

We can't actually run VS Code from CI, but we can:

* lint the manifest (every declared command must appear in the menu /
  activation-events lists too);
* verify the TypeScript entry imports the language-client and
  registers every advertised command + view;
* confirm the bundled REST helpers reference the configurable URL +
  token so a user override actually takes effect.
"""
import json
import re
from pathlib import Path

import pytest


_VSCODE_DIR = Path(__file__).resolve().parents[3] / "autocontrol-lsp" / "vscode"


def _manifest() -> dict:
    return json.loads(
        (_VSCODE_DIR / "package.json").read_text(encoding="utf-8"),
    )


def _extension_source() -> str:
    return (_VSCODE_DIR / "src" / "extension.ts").read_text(encoding="utf-8")


# === Manifest =============================================================

def test_manifest_advertises_run_screenshot_preview_commands():
    pkg = _manifest()
    names = {entry["command"] for entry in pkg["contributes"]["commands"]}
    assert {
        "autocontrol.runScript",
        "autocontrol.takeScreenshot",
        "autocontrol.previewScript",
    } <= names


def test_manifest_activation_events_cover_each_command():
    pkg = _manifest()
    events = set(pkg["activationEvents"])
    names = {entry["command"] for entry in pkg["contributes"]["commands"]}
    for command in names:
        assert f"onCommand:{command}" in events, (
            f"missing activation event for {command}"
        )


def test_manifest_declares_rest_config_properties():
    pkg = _manifest()
    props = pkg["contributes"]["configuration"]["properties"]
    assert "autocontrolLsp.rest.url" in props
    assert "autocontrolLsp.rest.token" in props
    assert props["autocontrolLsp.rest.url"]["default"].startswith("http")


def test_manifest_runs_command_pinned_to_json_files():
    pkg = _manifest()
    for menu_entry in pkg["contributes"]["menus"].get("editor/title", []):
        if menu_entry["command"] == "autocontrol.runScript":
            assert "resourceLangId == json" in menu_entry["when"]
            return
    pytest.fail("autocontrol.runScript not pinned to JSON editor title")


def test_manifest_registers_explorer_view():
    pkg = _manifest()
    explorer_views = pkg["contributes"]["views"]["explorer"]
    assert any(v["id"] == "autocontrolScriptSteps" for v in explorer_views)


def test_manifest_version_bumped_past_scaffold():
    """The scaffold shipped at 0.1.0; completion lifted us past that."""
    pkg = _manifest()
    major, minor, *_ = pkg["version"].split(".")
    assert (int(major), int(minor)) >= (0, 2)


# === Extension source ====================================================

def test_extension_registers_every_declared_command():
    source = _extension_source()
    for command in (
        "autocontrol.runScript",
        "autocontrol.takeScreenshot",
        "autocontrol.previewScript",
    ):
        assert f'registerCommand(\n            "{command}"' in source or \
            f'registerCommand("{command}"' in source, (
                f"extension.ts must register {command}"
            )


def test_extension_starts_language_client_with_python_module():
    source = _extension_source()
    assert "vscode-languageclient/node" in source
    assert "autocontrol_lsp.server" in source
    assert "TransportKind.stdio" in source


def test_extension_reads_rest_url_and_token_from_config():
    source = _extension_source()
    assert "rest.url" in source
    assert "rest.token" in source
    assert "AC_TOKEN" in source


def test_extension_treeview_uses_correct_view_id():
    source = _extension_source()
    assert "autocontrolScriptSteps" in source
    assert "registerTreeDataProvider" in source


def test_extension_only_posts_to_configurable_url():
    """No hardcoded https://example.com / http://localhost links."""
    source = _extension_source()
    hardcoded = re.findall(r'"https?://[^"]+"', source)
    # The only http literal allowed is in the comment / default fallback
    # path; everything else must come from config.
    for literal in hardcoded:
        assert literal in ('"http://127.0.0.1:9939"',), (
            f"unexpected hardcoded URL literal: {literal}"
        )


def test_extension_has_runtime_dependency_on_vscode_languageclient():
    pkg = _manifest()
    deps = {**pkg.get("dependencies", {}),
             **pkg.get("devDependencies", {})}
    assert "vscode-languageclient" in deps


def test_tsconfig_is_strict():
    raw = (_VSCODE_DIR / "tsconfig.json").read_text(encoding="utf-8")
    config = json.loads(raw)
    options = config["compilerOptions"]
    assert options["strict"] is True
    assert options["noImplicitAny"] is True
