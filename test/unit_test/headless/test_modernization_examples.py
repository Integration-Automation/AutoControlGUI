"""The new examples validate offline, and the docs agree with the code they describe.

Three things a reader relies on and nothing else checked:

* each example added with the platform / sync / mobile work has a ``--validate``
  path that runs to completion **without touching a device** -- run here as a
  child process under ``_example_guard.py``, which replaces every input,
  capture, process and network seam with a tripwire;
* every environment variable the package reads is in the configuration
  reference, in both languages, and the three READMEs name the same ones;
* ``docs/CAPABILITY_MATRIX.md`` says what ``probe_capabilities()`` and
  ``mobile_capability_matrix()`` say. Its two generated blocks are rewritten by
  ``python test/unit_test/headless/test_modernization_examples.py --fix``.
"""
import json
import os
import py_compile
import re
import subprocess  # nosec B404  # reason: runs this interpreter on repository files, fixed argv, no shell
import sys
import types
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = REPO_ROOT / "examples"
GUARD = Path(__file__).with_name("_example_guard.py")
MATRIX = REPO_ROOT / "docs" / "CAPABILITY_MATRIX.md"
CONFIG_PAGES = {
    "Eng": REPO_ROOT / "docs" / "source" / "Eng" / "doc" / "configuration" / "configuration_doc.rst",
    "Zh": REPO_ROOT / "docs" / "source" / "Zh" / "doc" / "configuration" / "configuration_doc.rst",
}
READMES = ("README.md", "README/README_zh-CN.md", "README/README_zh-TW.md")

NEW_EXAMPLES = (
    "28_wayland_diagnostics.py", "29_config_sync.py", "30_mobile_devices.py",
    "31_healing_comparison.py", "32_codegen_from_log.py", "33_mcp_progressive.py",
)

#: Variables the package reads that ``README.md`` does not mention. The README
#: is an overview and the configuration reference is the complete list, so
#: these are recorded rather than required -- but the set may not grow: a new
#: variable is either mentioned in the README or added here on purpose.
README_UNDOCUMENTED = frozenset({
    "AC_SIGNALING_CONFIG_DB", "AC_SIGNALING_SECRET",
    "JE_AUTOCONTROL_ACCEPT_LEGACY_ACTION_SIGNATURES",
    "JE_AUTOCONTROL_ACTION_SIGNING_PASSPHRASE", "JE_AUTOCONTROL_ACTION_SIGNING_PRIVATE_KEY",
    "JE_AUTOCONTROL_CHATOPS_SCRIPT_ROOT", "JE_AUTOCONTROL_ENV", "JE_AUTOCONTROL_FAKE_BACKEND",
    "JE_AUTOCONTROL_GUI_SETTINGS", "JE_AUTOCONTROL_INTERCEPTION_DLL",
    "JE_AUTOCONTROL_INTERCEPTION_KEYBOARD", "JE_AUTOCONTROL_INTERCEPTION_MOUSE",
    "JE_AUTOCONTROL_MCP_ALLOWED_ORIGINS", "JE_AUTOCONTROL_MCP_AUDIT",
    "JE_AUTOCONTROL_MCP_CONFIRM_DESTRUCTIVE", "JE_AUTOCONTROL_MCP_ERROR_SHOTS",
    "JE_AUTOCONTROL_MCP_READONLY", "JE_AUTOCONTROL_MCP_TOKEN", "JE_AUTOCONTROL_MCP_TOOL_MODE",
    "JE_AUTOCONTROL_MCP_TOOL_PROFILE", "JE_AUTOCONTROL_PYTEST_ARTIFACTS",
    "JE_AUTOCONTROL_REDACTION", "JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS",
    "JE_AUTOCONTROL_USB_PASSTHROUGH", "JE_AUTOCONTROL_WAYLAND_EI_WORKER",
    "JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND", "JE_AUTOCONTROL_WAYLAND_RECORD_DEVICES",
})

_ENV_NAME = re.compile(r"\b(?:JE_AUTOCONTROL|AC_SIGNALING)_[A-Z0-9_]+\b")
_BLOCK = "<!-- {name}:{edge} (generated: test_modernization_examples.py --fix) -->"


# --- examples -------------------------------------------------------------

def _run_guarded(script: Path, arguments: List[str], tmp_path: Path) -> Tuple[int, List[str], str]:
    """Run ``script`` under the guard; ``(exit code, device effects, output)``."""
    effects_file = tmp_path / "effects.json"
    env = dict(os.environ)
    env.update({"PYTHONPATH": str(REPO_ROOT), "PYTHONIOENCODING": "utf-8",
                "AC_EXAMPLE_GUARD_EFFECTS": str(effects_file),
                "JE_AUTOCONTROL_LOG_FILE": os.devnull, "JE_AUTOCONTROL_GUI_SETTINGS": "off",
                "HOME": str(tmp_path), "USERPROFILE": str(tmp_path)})
    for name in ("JE_AUTOCONTROL_RBAC_USERS", "JE_AUTOCONTROL_MCP_TOOL_MODE",
                 "JE_AUTOCONTROL_MCP_READONLY", "AC_SIGNALING_SECRET"):
        env.pop(name, None)
    done = subprocess.run(  # nosec B603  # nosemgrep  # reason: this interpreter, repository files, no shell
        [sys.executable, str(GUARD), str(script), *arguments],
        cwd=tmp_path, env=env, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=180, check=False)
    effects = json.loads(effects_file.read_text(encoding="utf-8")) if effects_file.exists() else [
        "the guard never started"]
    return done.returncode, effects, done.stdout + done.stderr


@pytest.mark.parametrize("name", NEW_EXAMPLES)
def test_examples_compile_and_validate_without_device(name, tmp_path):
    script = EXAMPLES / name
    py_compile.compile(str(script), cfile=str(tmp_path / "compiled.pyc"), doraise=True)
    source = script.read_text(encoding="utf-8")
    assert '"--validate"' in source, f"{name} offers no --validate"
    code, device_effects_in_validate, output = _run_guarded(script, ["--validate"], tmp_path)
    assert device_effects_in_validate == [], output
    assert code == 0, output
    assert "validate: ok" in output


def test_every_numbered_example_is_listed_in_the_examples_readme():
    listed = set(re.findall(r"\[`(\d\d_[a-z0-9_]+\.py)`\]", (EXAMPLES / "README.md").read_text(
        encoding="utf-8")))
    on_disk = {path.name for path in EXAMPLES.glob("[0-9][0-9]_*.py")}
    assert on_disk - listed == set(), "examples missing from examples/README.md"
    assert listed - on_disk == set(), "examples/README.md lists scripts that do not exist"
    assert set(NEW_EXAMPLES) <= on_disk


def test_the_guard_trips_on_a_backend_function():
    """The guard is only evidence if a replaced function really refuses to run."""
    from headless import _example_guard as guard
    module = types.ModuleType("fake_backend")

    def set_position(x, y):
        return x, y

    set_position.__module__ = module.__name__
    module.set_position = set_position
    module.CONSTANT = 3
    assert guard.tripwire_module(module) == 1
    before = len(guard.effects())
    with pytest.raises(guard.DeviceEffect):
        module.set_position(1, 2)
    assert guard.effects()[before:] == ["backend: fake_backend.set_position"]
    assert module.CONSTANT == 3


@pytest.mark.parametrize("body, kind", [
    # Harmless even if the guard failed: the child only starts `python -c pass`.
    ("import subprocess, sys\n"
     "try:\n    subprocess.run([sys.executable, '-c', 'pass'])\n"
     "except Exception:\n    pass\n", "process"),
    # 192.0.2.0/24 is TEST-NET-1: never routed, so an unguarded attempt goes nowhere.
    ("import socket\ns = socket.socket()\ns.settimeout(0.2)\n"
     "try:\n    s.connect(('192.0.2.1', 9))\nexcept Exception:\n    pass\n", "network"),
])
def test_the_guard_reports_an_effect_the_script_swallowed(body, kind, tmp_path):
    script = tmp_path / "probe.py"
    script.write_text(body, encoding="utf-8")
    code, effects, output = _run_guarded(script, [], tmp_path)
    assert code == 0, output
    assert len(effects) == 1 and effects[0].startswith(f"{kind}: "), effects


def test_the_guard_allows_loopback(tmp_path):
    script = tmp_path / "probe.py"
    script.write_text(
        "import socket\nserver = socket.socket()\nserver.bind(('127.0.0.1', 0))\nserver.listen(1)\n"
        "client = socket.socket()\nclient.connect(server.getsockname())\nprint('connected')\n",
        encoding="utf-8")
    code, effects, output = _run_guarded(script, [], tmp_path)
    assert (code, effects) == (0, []) and "connected" in output, output


# --- configuration --------------------------------------------------------

def _names(paths: Iterable[Path]) -> Set[str]:
    found: Set[str] = set()
    for path in paths:
        found |= set(_ENV_NAME.findall(path.read_text(encoding="utf-8", errors="replace")))
    return found


def _names_in_code() -> Set[str]:
    sources = [path for path in (REPO_ROOT / "je_auto_control").rglob("*.py")
               if "__pycache__" not in path.parts]
    return _names([*sources, REPO_ROOT / "je_auto_control_pytest.py"])


def test_readme_configuration_parity():
    in_code = _names_in_code()
    english_configuration_keys = _names([CONFIG_PAGES["Eng"]])
    translated_configuration_keys = _names([CONFIG_PAGES["Zh"]])
    assert translated_configuration_keys == english_configuration_keys
    assert in_code - english_configuration_keys == set(), (
        "read by the package and missing from the configuration reference (both languages)")
    assert english_configuration_keys - in_code == set(), (
        "documented in the configuration reference and read by nothing")

    readme, simplified, traditional = (_names([REPO_ROOT / name]) for name in READMES)
    assert simplified == readme and traditional == readme, (
        "the three READMEs name different environment variables")
    assert readme - in_code == set(), "README.md names a variable nothing reads"
    assert (in_code - readme) - README_UNDOCUMENTED == set(), (
        "a new variable is in neither README.md nor README_UNDOCUMENTED")


def test_the_configuration_page_is_reachable_in_both_languages():
    for language, index in (("Eng", "eng_index.rst"), ("Zh", "zh_index.rst")):
        toctree = (REPO_ROOT / "docs" / "source" / language / index).read_text(encoding="utf-8")
        for page in ("doc/configuration/configuration_doc", "doc/examples/examples_doc"):
            assert f"   {page}\n" in toctree.replace("\r\n", "\n"), f"{page} not in {index}"
            assert (REPO_ROOT / "docs" / "source" / language / f"{page}.rst").is_file()


# --- capability matrix ----------------------------------------------------

def _described_sessions() -> List[Tuple[str, str, Dict[str, object]]]:
    """``(platform, what is described, facts)``: sessions given as facts, never read here.

    The table has to be the same on every runner, so nothing in it comes from
    the machine that generates it.
    """
    usual = {"integrity": "medium", "session_id": 1, "input_desktop": "Default",
             "hook_access": True, "capture_ok": True}
    return [
        ("win32", "signed-in session, medium integrity", usual),
        ("win32", "elevated (high integrity)", {**usual, "integrity": "high"}),
        ("win32", "low integrity", {**usual, "integrity": "low"}),
        ("win32", "workstation locked (input desktop `Winlogon`)",
         {**usual, "input_desktop": "Winlogon"}),
        ("win32", "session 0 (a service)", {**usual, "session_id": 0}),
        ("win32", "1x1 screen copy fails", {**usual, "capture_ok": False}),
        ("win32", "nothing could be read", {}),
        ("darwin", "Accessibility, Screen Recording and Input Monitoring granted",
         {"accessibility": True, "screen_recording": True, "input_monitoring": True}),
        ("darwin", "only Accessibility granted",
         {"accessibility": True, "screen_recording": False, "input_monitoring": False}),
        ("darwin", "nothing granted",
         {"accessibility": False, "screen_recording": False, "input_monitoring": False}),
        ("darwin", "preflight calls not available", {}),
    ]


def _probe_rows() -> List[Dict[str, str]]:
    """What ``probe_capabilities()`` concludes from each described session."""
    from je_auto_control.wrapper.capabilities import BackendContext, probe_capabilities
    from je_auto_control.wrapper.capability_probes import MacFacts, WindowsFacts
    rows = []
    for platform, described, facts in _described_sessions():
        snapshot = probe_capabilities(BackendContext(
            platform=platform, environ={},
            windows_facts=lambda facts=facts: WindowsFacts(**facts),
            mac_facts=lambda facts=facts: MacFacts(**facts),
            backend_version=lambda _backend: ""))
        rows.append({"platform": platform, "described": described,
                     **{item.name: item.state.value for item in snapshot.capabilities}})
    return rows


def render_probe_block() -> str:
    """The generated table of ``probe_capabilities()`` on Windows and macOS."""
    names = ("input", "capture", "recording", "stop_shortcut")
    lines = ["| Platform | Session described | " + " | ".join(f"`{name}`" for name in names) + " |",
             "|---|---|---|---|---|---|"]
    for row in _probe_rows():
        states = " | ".join(f"`{row[name]}`" for name in names)
        lines.append(f"| `{row['platform']}` | {row['described']} | {states} |")
    return "\n".join(lines)


def render_mobile_block() -> str:
    """The generated tables of ``mobile_capability_matrix()``."""
    from je_auto_control.wrapper.mobile_commands import mobile_capability_matrix
    matrix = mobile_capability_matrix()

    def commands(names: List[str]) -> str:
        return ", ".join(f"`{name}`" for name in names) or "—"

    lines = ["| Capability | Android commands | iOS commands |", "|---|---|---|"]
    lines += [f"| `{row['capability']}` | {commands(row['android'])} | {commands(row['ios'])} |"
              for row in matrix["capabilities"]]
    lines += ["", "| Desktop-only feature | Why | Use instead |", "|---|---|---|"]
    lines += [f"| {row['feature']} | {row['limitation']} | {row['alternative']} |"
              for row in matrix["desktop_only"]]
    return "\n".join(lines)


GENERATED = {"probe-capabilities": render_probe_block, "mobile-matrix": render_mobile_block}


def _block(text: str, name: str) -> str:
    begin, end = (_BLOCK.format(name=name, edge=edge) for edge in ("begin", "end"))
    assert text.count(begin) == 1 and text.count(end) == 1, f"markers of {name} are missing"
    return text.split(begin, 1)[1].split(end, 1)[0].strip("\n")


def _matrix_text() -> str:
    return MATRIX.read_text(encoding="utf-8").replace("\r\n", "\n")


@pytest.mark.parametrize("name", sorted(GENERATED))
def test_matrix_matches_capabilities(name):
    assert _block(_matrix_text(), name) == GENERATED[name](), (
        "re-generate: python test/unit_test/headless/test_modernization_examples.py --fix")


def test_matrix_names_every_capability_and_state():
    from je_auto_control.linux_wayland.authorisation import CAPTURE, INPUT
    from je_auto_control.wrapper import device_context
    from je_auto_control.wrapper.capabilities import RECORDING, STOP_SHORTCUT, CapabilityStatus
    text = _matrix_text()
    wanted = {INPUT, CAPTURE, RECORDING, STOP_SHORTCUT, *device_context.CAPABILITY_NAMES,
              *(status.value for status in CapabilityStatus),
              device_context.STATE_AVAILABLE, device_context.STATE_NEEDS_PERMISSION,
              device_context.STATE_NEEDS_DEPENDENCY, device_context.STATE_UNSUPPORTED}
    undocumented_capabilities = {name for name in wanted if f"`{name}`" not in text}
    assert undocumented_capabilities == set()


def test_matrix_does_not_claim_hardware_for_mobile():
    """The mobile row stays honest until a job drives a real device."""
    row = next(line for line in _matrix_text().splitlines()
               if line.startswith("| Android and iOS bridges"))
    assert "mocked CI" in row and "hardware" not in row.replace("hardware-unverified", "")


def _fix() -> None:
    text = _matrix_text()
    for name, render in GENERATED.items():
        begin, end = (_BLOCK.format(name=name, edge=edge) for edge in ("begin", "end"))
        head, rest = text.split(begin, 1)
        _old, tail = rest.split(end, 1)
        text = f"{head}{begin}\n{render()}\n{end}{tail}"
    MATRIX.write_text(text, encoding="utf-8", newline="\n")
    print(f"rewrote the generated blocks of {MATRIX.name}; review the diff")


if __name__ == "__main__":
    sys.path.insert(0, str(REPO_ROOT))
    if sys.argv[1:] == ["--fix"]:
        _fix()
    else:
        raise SystemExit("usage: test_modernization_examples.py --fix")
