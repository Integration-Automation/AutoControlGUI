"""File boundaries: MCP tool paths, value references and viewer downloads.

Three places took a path from the other side of a trust boundary and used it
as given. An MCP tool's file argument reached any file on the machine, even in
read-only mode (``ac_load_dotenv`` returned any file as KEY=VALUE).
``ac_resolve_ref`` read any environment variable and any file. And a remote
desktop viewer wrote a host-pushed file wherever the host said.

The first two are opt-in — a server nobody configured must behave as before —
so each has a test for the unconfigured case as well as the confined one.
"""
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import pytest

from je_auto_control.utils.mcp_server._argument_policy import ArgumentPolicy
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools import MCPTool, build_default_tool_registry
from je_auto_control.utils.path_guard import PathNotAllowedError, PathPolicy
from je_auto_control.utils.path_guard.policy import (
    MCP_CLIENT_ROOTS_ENV, MCP_PATH_ROOTS_ENV,
)
from je_auto_control.utils.remote_desktop.file_transfer import (
    DOWNLOAD_DIR_ENV, FileReceiver, FileTransferError, confine_destination,
    default_download_dir, encode_begin, encode_chunk, encode_end, new_transfer_id,
)
from je_auto_control.utils.secret_ref import (
    MCP_ENV_REF_ALLOW_ENV, RefResolver, SecretRefError, env_allowlist_from_env,
)

_POLICY_ENV = (MCP_PATH_ROOTS_ENV, MCP_CLIENT_ROOTS_ENV, MCP_ENV_REF_ALLOW_ENV)


@pytest.fixture(autouse=True)
def _no_ambient_policy(monkeypatch):
    """A developer's own environment must not configure the servers under test."""
    for name in _POLICY_ENV + (DOWNLOAD_DIR_ENV,):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(scope="module")
def registry() -> Dict[str, MCPTool]:
    return {tool.name: tool
            for tool in build_default_tool_registry(read_only=False, aliases=False)}


def _path_pointers(schema: Dict[str, Any], prefix: str = "") -> Iterator[str]:
    """Every place in ``schema`` annotated ``"format": "path"``."""
    if schema.get("format") == "path":
        yield prefix
    for key, child in (schema.get("properties") or {}).items():
        yield from _path_pointers(child, f"{prefix}.{key}" if prefix else key)
    for key in ("items", "additionalProperties"):
        if isinstance(schema.get(key), dict):
            yield from _path_pointers(schema[key], f"{prefix}[]")


def _call(server: MCPServer, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    line = server.handle_line(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }))
    return json.loads(line)["result"]


def _text(result: Dict[str, Any]) -> str:
    return "".join(block.get("text", "") for block in result["content"])


def _server(names: List[str], *, read_only: bool = False) -> MCPServer:
    tools = [tool for tool in build_default_tool_registry(read_only=read_only, aliases=False)
             if tool.name in names]
    assert {tool.name for tool in tools} == set(names)
    return MCPServer(tools=tools)


def _symlink(link: Path, target: Path) -> None:
    """Link ``link`` to ``target``; a directory falls back to an NTFS junction."""
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError):
        if sys.platform != "win32" or not target.is_dir():
            pytest.skip("this account cannot create symlinks")
        import _winapi
        _winapi.CreateJunction(str(target), str(link))


# --- which arguments are paths --------------------------------------------

@pytest.mark.parametrize("name, pointer", [
    ("ac_load_dotenv", "path"), ("ac_read_document", "path"),
    ("ac_extract_pdf_text", "path"), ("ac_sql_query", "database"),
    ("ac_read_action_file", "file_path"), ("ac_screenshot", "file_path"),
    ("ac_queue_stats", "db"), ("ac_match_template", "template"),
    ("ac_ssim_compare", "reference"), ("ac_anchor_locate", "anchor.template_path"),
    ("ac_set_clipboard_files", "paths[]"), ("ac_build_provenance", "paths[]"),
    ("ac_verify_provenance", "files[]"), ("ac_load_data", "source.path"),
    ("ac_write_step_video", "steps[].image"), ("ac_send_email", "message.attachments[]"),
    ("ac_generate_code", "source"),
])
def test_file_arguments_are_marked_as_paths(registry, name, pointer):
    assert pointer in set(_path_pointers(registry[name].input_schema))


@pytest.mark.parametrize("name, argument", [
    ("ac_json_query", "path"),            # a JSONPath expression
    ("ac_handle_file_dialog", "path"),    # keystrokes typed into another app's dialog
    ("ac_queue_complete", "output"),      # the work item's result
    ("ac_queue_add", "reference"),        # a dedupe key
    ("ac_cua_command", "source"),         # anthropic / openai / canonical
    ("ac_generate_sbom", "root"),         # a distribution name
    ("ac_gettext_translate", "po"),       # the .po text itself
    ("ac_perceptual_diff", "min_area"),
])
def test_semantic_path_fields_only(registry, name, argument):
    """The annotation follows meaning: a property merely called ``path`` is left alone."""
    assert argument not in set(_path_pointers(registry[name].input_schema))


def test_aliases_carry_the_same_annotations():
    tools = {tool.name: tool for tool in build_default_tool_registry(aliases=True)}
    assert "file_path" in set(_path_pointers(tools["screenshot"].input_schema))


# --- PathPolicy -----------------------------------------------------------

def test_policy_without_roots_restricts_nothing(tmp_path):
    policy = PathPolicy()
    assert not policy.enabled
    assert policy.validate(tmp_path / "x", operation="t") == Path(os.path.realpath(tmp_path / "x"))


def test_policy_accepts_inside_and_rejects_outside(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    policy = PathPolicy([root])
    assert policy.validate(root / "a" / "b.txt", operation="t") == \
        Path(os.path.realpath(root / "a" / "b.txt"))
    assert policy.validate(root, operation="t") == Path(os.path.realpath(root))
    with pytest.raises(PathNotAllowedError, match="tool x"):
        policy.validate(tmp_path / "other.txt", operation="tool x")


@pytest.mark.parametrize("escape", ["..", "sub/../../outside.txt", "./../x"])
def test_policy_rejects_dot_dot_escape(tmp_path, escape):
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(PathNotAllowedError):
        PathPolicy([root]).validate(str(root / escape), operation="t")


def test_symlink_escape_is_rejected(tmp_path):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("s", encoding="utf-8")
    _symlink(root / "link", outside)
    policy = PathPolicy([root])
    with pytest.raises(PathNotAllowedError):
        policy.validate(root / "link" / "secret.txt", operation="t")
    _symlink(root / "file_link", outside / "secret.txt")
    with pytest.raises(PathNotAllowedError):
        policy.validate(root / "file_link", operation="t")


@pytest.mark.skipif(sys.platform != "win32", reason="drive and UNC paths are Windows forms")
@pytest.mark.parametrize("path", [
    r"\\server\share\x.txt", r"\\?\UNC\server\share\x.txt", r"\\.\NUL", "NUL",
    "Z:\\x.txt", "Z:x.txt",
])
def test_drive_and_unc_escapes_are_rejected(tmp_path, monkeypatch, path):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.chdir(root)
    with pytest.raises(PathNotAllowedError):
        PathPolicy([root]).validate(path, operation="t")


def test_tilde_must_be_inside_both_expanded_and_literal(tmp_path, monkeypatch):
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir()
    cwd.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.chdir(cwd)
    with pytest.raises(PathNotAllowedError):   # a handler that expands it leaves the root
        PathPolicy([cwd]).validate("~/x.txt", operation="t")
    with pytest.raises(PathNotAllowedError):   # a handler that does not leaves it too
        PathPolicy([home]).validate("~/x.txt", operation="t")
    assert PathPolicy([home, cwd]).validate("~/x.txt", operation="t") == \
        Path(os.path.realpath(home / "x.txt"))


@pytest.mark.parametrize("bad", ["", "a\x00b"])
def test_policy_rejects_malformed_paths(tmp_path, bad):
    with pytest.raises(PathNotAllowedError):
        PathPolicy([tmp_path]).validate(bad, operation="t")


def test_policy_from_env(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    assert not PathPolicy.from_env({}).enabled
    policy = PathPolicy.from_env({MCP_PATH_ROOTS_ENV: f"{first}{os.pathsep} {second} {os.pathsep}"})
    assert policy.roots() == (Path(os.path.realpath(first)), Path(os.path.realpath(second)))
    assert not policy.use_client_roots
    assert PathPolicy.from_env({MCP_CLIENT_ROOTS_ENV: "1"}).use_client_roots
    assert not PathPolicy.from_env({MCP_CLIENT_ROOTS_ENV: "0"}).enabled


def test_client_roots_need_the_opt_in_and_fail_closed_until_known(tmp_path):
    ignored = PathPolicy()
    ignored.set_client_roots([tmp_path])
    assert ignored.roots() == ()
    assert not ignored.enabled

    policy = PathPolicy(use_client_roots=True)
    assert policy.enabled
    with pytest.raises(PathNotAllowedError, match="none known yet"):
        policy.validate(tmp_path / "x", operation="t")
    policy.set_client_roots([tmp_path])
    assert policy.validate(tmp_path / "x", operation="t")
    policy.set_client_roots([])
    with pytest.raises(PathNotAllowedError):
        policy.validate(tmp_path / "x", operation="t")


# --- the walk over a tool's arguments --------------------------------------

_SCHEMA = {"type": "object", "properties": {
    "path": {"type": "string", "format": "path"},
    "expr": {"type": "string"},
    "many": {"type": "array", "items": {"format": "path"}},
    "spec": {"type": "object", "properties": {"path": {"format": "path"}}},
    "files": {"type": "object", "additionalProperties": {"format": "path"}},
    "source": {"type": ["array", "string"], "format": "path"},
}}


def test_walk_canonicalises_every_marked_path_and_nothing_else(tmp_path):
    policy = ArgumentPolicy(PathPolicy([tmp_path]))
    inside = str(tmp_path / "sub" / ".." / "a.txt")
    real = os.path.realpath(tmp_path / "a.txt")
    out = policy.apply("tool", _SCHEMA, {
        "path": inside, "expr": "../../$.a", "many": [inside], "spec": {"path": inside, "kind": "csv"},
        "files": {"x": inside}, "source": [["AC_noop", {"path": "/elsewhere"}]],
    })
    assert out == {"path": real, "expr": "../../$.a", "many": [real],
                   "spec": {"path": real, "kind": "csv"}, "files": {"x": real},
                   "source": [["AC_noop", {"path": "/elsewhere"}]]}


@pytest.mark.parametrize("arguments, where", [
    ({"path": "OUT"}, "tool $.path"), ({"many": ["OUT"]}, r"tool \$\.many\[0\]"),
    ({"spec": {"path": "OUT"}}, "tool $.spec.path"), ({"files": {"x": "OUT"}}, "tool $.files.x"),
    ({"source": "OUT"}, "tool $.source"),
])
def test_walk_rejects_an_outside_path_wherever_it_sits(tmp_path, arguments, where):
    root = tmp_path / "root"
    root.mkdir()
    outside = str(tmp_path / "outside.txt")
    text = json.dumps(arguments).replace("OUT", outside.replace("\\", "\\\\"))
    with pytest.raises(PathNotAllowedError, match=where.replace("$", r"\$") if "\\" not in where
                       else where):
        ArgumentPolicy(PathPolicy([root])).apply("tool", _SCHEMA, json.loads(text))


def test_walk_leaves_an_empty_path_to_the_handler(tmp_path):
    arguments = {"path": ""}
    assert ArgumentPolicy(PathPolicy([tmp_path])).apply("tool", _SCHEMA, arguments) == arguments


def test_unconfigured_walk_returns_the_arguments_untouched():
    arguments = {"path": "../x"}
    assert ArgumentPolicy().apply("tool", _SCHEMA, arguments) is arguments


# --- through the server ----------------------------------------------------

def _dotenv(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "app.env"
    target.write_text("TOKEN=abc\n", encoding="utf-8")
    return target


def test_unconfigured_server_reads_anywhere_even_read_only(tmp_path):
    """The default is unchanged: no roots, no restriction, read-only included."""
    target = _dotenv(tmp_path / "elsewhere")
    server = _server(["ac_load_dotenv"], read_only=True)
    assert not server.argument_policy.enabled
    result = _call(server, "ac_load_dotenv", {"path": str(target)})
    assert result["isError"] is False
    assert "abc" in _text(result)


def test_configured_roots_reject_a_path_outside_them(tmp_path, monkeypatch):
    root = tmp_path / "root"
    inside = _dotenv(root)
    outside = _dotenv(tmp_path / "elsewhere")
    monkeypatch.setenv(MCP_PATH_ROOTS_ENV, str(root))
    server = _server(["ac_load_dotenv"], read_only=True)

    escaped = _call(server, "ac_load_dotenv", {"path": str(outside)})
    assert escaped["isError"] is True
    assert "Invalid arguments for ac_load_dotenv" in _text(escaped)
    assert "abc" not in _text(escaped)
    dotted = _call(server, "ac_load_dotenv", {"path": str(root / ".." / "elsewhere" / "app.env")})
    assert dotted["isError"] is True

    allowed = _call(server, "ac_load_dotenv", {"path": str(inside)})
    assert allowed["isError"] is False
    assert "abc" in _text(allowed)


def test_configured_roots_leave_a_json_path_alone(tmp_path, monkeypatch):
    monkeypatch.setenv(MCP_PATH_ROOTS_ENV, str(tmp_path))
    server = _server(["ac_json_query"])
    result = _call(server, "ac_json_query", {"data": {"a": {"b": 7}}, "path": "$.a.b"})
    assert result["isError"] is False
    assert "7" in _text(result)


def test_server_rejects_a_symlink_out_of_the_roots(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    _dotenv(tmp_path / "elsewhere")
    _symlink(root / "link", tmp_path / "elsewhere")
    monkeypatch.setenv(MCP_PATH_ROOTS_ENV, str(root))
    result = _call(_server(["ac_load_dotenv"]), "ac_load_dotenv",
                   {"path": str(root / "link" / "app.env")})
    assert result["isError"] is True
    assert "abc" not in _text(result)


def test_roots_list_feeds_the_policy_only_when_opted_in(tmp_path, monkeypatch):
    workspace = tmp_path / "ws"
    inside = _dotenv(workspace)
    outside = _dotenv(tmp_path / "elsewhere")
    uri = "file:///" + str(workspace).replace("\\", "/").lstrip("/")
    reply = {"roots": [{"uri": uri}, {"uri": "https://example.invalid/x"}, "junk"]}

    plain = _server(["ac_load_dotenv"])
    monkeypatch.setattr(plain, "_send_outbound_request", lambda *args, **kwargs: reply)
    plain.refresh_roots()
    assert _call(plain, "ac_load_dotenv", {"path": str(outside)})["isError"] is False

    monkeypatch.setenv(MCP_CLIENT_ROOTS_ENV, "true")
    server = _server(["ac_load_dotenv"])
    assert _call(server, "ac_load_dotenv", {"path": str(inside)})["isError"] is True
    monkeypatch.setattr(server, "_send_outbound_request", lambda *args, **kwargs: reply)
    server.refresh_roots()
    assert server.argument_policy.path_policy.roots() == (Path(os.path.realpath(workspace)),)
    assert _call(server, "ac_load_dotenv", {"path": str(inside)})["isError"] is False
    assert _call(server, "ac_load_dotenv", {"path": str(outside)})["isError"] is True


def test_env_roots_and_client_roots_add_up(tmp_path, monkeypatch):
    configured, reported = tmp_path / "configured", tmp_path / "reported"
    monkeypatch.setenv(MCP_PATH_ROOTS_ENV, str(configured))
    monkeypatch.setenv(MCP_CLIENT_ROOTS_ENV, "1")
    policy = ArgumentPolicy.from_env().path_policy
    policy.set_client_roots([reported])
    assert policy.validate(configured / "a", operation="t")
    assert policy.validate(reported / "a", operation="t")


# --- value references ------------------------------------------------------

def test_env_ref_allowlist():
    env = {"APP_URL": "u", "APP_KEY": "k", "ANTHROPIC_API_KEY": "sk"}
    assert RefResolver(env=env).resolve("env://ANTHROPIC_API_KEY") == "sk"
    limited = RefResolver(env=env, env_allowlist=["APP_*", "HOME"])
    assert limited.resolve("env://APP_URL") == "u"
    with pytest.raises(SecretRefError, match="allowlist"):
        limited.resolve("env://ANTHROPIC_API_KEY")
    with pytest.raises(SecretRefError, match="allowlist"):
        limited.check_all({"a": [{"b": "env://ANTHROPIC_API_KEY"}]})
    limited.check_all({"a": ["env://APP_KEY", "plain", 3, "secret://x"]})
    with pytest.raises(SecretRefError):
        RefResolver(env=env, env_allowlist=[]).resolve("env://APP_URL")


@pytest.mark.parametrize("raw, expected", [
    (None, None), ("", None), ("  ", None), ("A, B_*", ("A", "B_*")), (",", ()),
])
def test_env_allowlist_from_env(raw: Optional[str], expected: Optional[Tuple[str, ...]]):
    environ = {} if raw is None else {MCP_ENV_REF_ALLOW_ENV: raw}
    assert env_allowlist_from_env(environ) == expected


def test_file_ref_follows_the_path_policy(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "ok.txt").write_text("fine", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("no", encoding="utf-8")
    resolver = RefResolver(path_policy=PathPolicy([root]))
    assert resolver.resolve("file://" + str(root / "ok.txt").replace("\\", "/")) == "fine"
    outside = "file://" + str(tmp_path / "secret.txt").replace("\\", "/")
    with pytest.raises(SecretRefError, match="outside the allowed roots"):
        resolver.resolve(outside)
    with pytest.raises(SecretRefError):
        resolver.check_all([outside])
    assert RefResolver(path_policy=PathPolicy()).resolve(outside) == "no"


def test_unconfigured_server_resolves_any_env_ref(monkeypatch):
    monkeypatch.setenv("AC_TEST_BOUNDARY_VALUE", "visible")
    result = _call(_server(["ac_resolve_ref"]), "ac_resolve_ref",
                   {"ref": "env://AC_TEST_BOUNDARY_VALUE"})
    assert result["isError"] is False
    assert "visible" in _text(result)


def test_server_applies_the_env_allowlist_to_both_ref_tools(monkeypatch):
    monkeypatch.setenv("AC_TEST_BOUNDARY_VALUE", "visible")
    monkeypatch.setenv("AC_TEST_BOUNDARY_SECRET", "hidden")
    monkeypatch.setenv(MCP_ENV_REF_ALLOW_ENV, "AC_TEST_BOUNDARY_VALUE")
    server = _server(["ac_resolve_ref", "ac_resolve_refs"])
    allowed = _call(server, "ac_resolve_ref", {"ref": "env://AC_TEST_BOUNDARY_VALUE"})
    assert allowed["isError"] is False
    assert "visible" in _text(allowed)
    for name, arguments in [
        ("ac_resolve_ref", {"ref": "env://AC_TEST_BOUNDARY_SECRET"}),
        ("ac_resolve_refs", {"obj": {"k": ["env://AC_TEST_BOUNDARY_SECRET"]}}),
    ]:
        refused = _call(server, name, arguments)
        assert refused["isError"] is True
        assert "allowlist" in _text(refused)
        assert "hidden" not in _text(refused)


def test_server_applies_the_roots_to_file_refs(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    (root / "ok.txt").write_text("fine", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("leak", encoding="utf-8")
    monkeypatch.setenv(MCP_PATH_ROOTS_ENV, str(root))
    server = _server(["ac_resolve_ref", "ac_resolve_refs"])
    inside = "file://" + str(root / "ok.txt").replace("\\", "/")
    outside = "file://" + str(tmp_path / "secret.txt").replace("\\", "/")
    assert "fine" in _text(_call(server, "ac_resolve_ref", {"ref": inside}))
    for name, arguments in [("ac_resolve_ref", {"ref": outside}),
                            ("ac_resolve_refs", {"obj": {"k": outside}})]:
        refused = _call(server, name, arguments)
        assert refused["isError"] is True
        assert "leak" not in _text(refused)


# --- viewer downloads ------------------------------------------------------

def _receive(receiver: FileReceiver, dest_path: str, data: bytes = b"payload") -> None:
    transfer_id = new_transfer_id()
    receiver.handle_begin(encode_begin(transfer_id, dest_path, len(data)))
    receiver.handle_chunk(encode_chunk(transfer_id, data))
    receiver.handle_end(encode_end(transfer_id))


def _confined(base: Path) -> Tuple[FileReceiver, List[Tuple[bool, Optional[str], str]]]:
    outcomes: List[Tuple[bool, Optional[str], str]] = []
    receiver = FileReceiver(
        on_complete=lambda _tid, ok, error, dest: outcomes.append((ok, error, dest)),
        base_dir=base)
    return receiver, outcomes


def test_viewer_file_stays_in_download_root(tmp_path):
    download_root = tmp_path / "downloads"
    receiver, outcomes = _confined(download_root)
    _receive(receiver, "reports/2026\\q3/out.bin")
    received_path = Path(outcomes[-1][2])
    assert outcomes[-1][:2] == (True, None)
    assert received_path.is_relative_to(Path(os.path.realpath(download_root)))
    assert received_path == Path(os.path.realpath(download_root / "reports" / "2026" / "q3" / "out.bin"))
    assert received_path.read_bytes() == b"payload"
    assert not list(download_root.rglob("*.part"))


_ESCAPES = ["/tmp/from_host.bin", "/etc/cron.d/x", "C:\\Windows\\x.dll", "C:x.dll", "c:/x",
            "\\\\server\\share\\x", "//server/share/x", "\\x.bin", "../x.bin", "a/../../x.bin",
            "a\\..\\..\\x.bin", "..", ".", "", "a/..", "./"]


@pytest.mark.parametrize("dest_path", [path for path in _ESCAPES if path])
def test_viewer_refuses_a_destination_outside_the_download_root(tmp_path, dest_path):
    download_root = tmp_path / "downloads"
    receiver, outcomes = _confined(download_root)
    _receive(receiver, dest_path)
    assert len(outcomes) == 1
    assert outcomes[0][0] is False
    assert outcomes[0][2] == dest_path
    written = [path for path in tmp_path.rglob("*") if path.is_file()]
    assert written == []


@pytest.mark.parametrize("dest_path", _ESCAPES)
def test_confine_destination_raises_for_every_escape(tmp_path, dest_path):
    with pytest.raises(FileTransferError):
        confine_destination(tmp_path, dest_path)


def test_viewer_refuses_a_symlink_out_of_the_download_root(tmp_path):
    download_root = tmp_path / "downloads"
    outside = tmp_path / "outside"
    download_root.mkdir()
    outside.mkdir()
    (outside / "victim.txt").write_text("original", encoding="utf-8")
    _symlink(download_root / "dir_link", outside)
    receiver, outcomes = _confined(download_root)
    _receive(receiver, "dir_link/new.bin")
    _receive(receiver, "dir_link/victim.txt")
    assert [outcome[0] for outcome in outcomes] == [False, False]
    assert (outside / "victim.txt").read_text(encoding="utf-8") == "original"
    assert sorted(path.name for path in outside.iterdir()) == ["victim.txt"]
    _symlink(download_root / "file_link", outside / "victim.txt")
    _receive(receiver, "file_link")
    assert outcomes[-1][0] is False
    assert (outside / "victim.txt").read_text(encoding="utf-8") == "original"


def test_receiver_without_base_dir_keeps_the_host_side_behaviour(tmp_path):
    """The host trusts its authenticated viewers: an absolute path is honoured."""
    outcomes: List[Tuple[bool, Optional[str], str]] = []
    receiver = FileReceiver(on_complete=lambda _t, ok, err, dst: outcomes.append((ok, err, dst)))
    target = tmp_path / "anywhere" / "a.bin"
    _receive(receiver, str(target))
    assert outcomes == [(True, None, str(target))]
    assert target.read_bytes() == b"payload"


def test_default_download_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert default_download_dir() == tmp_path / "Downloads" / "AutoControl"
    monkeypatch.setenv(DOWNLOAD_DIR_ENV, str(tmp_path / "inbox"))
    assert default_download_dir() == tmp_path / "inbox"


def test_viewer_default_receiver_is_confined_and_host_default_is_not(tmp_path, monkeypatch):
    from je_auto_control.utils.remote_desktop import RemoteDesktopHost, RemoteDesktopViewer
    monkeypatch.setenv(DOWNLOAD_DIR_ENV, str(tmp_path / "inbox"))
    viewer = RemoteDesktopViewer(host="127.0.0.1", port=1, token="t")
    receiver = viewer._ensure_file_receiver()
    _receive(receiver, str(tmp_path / "absolute.bin"))
    assert not (tmp_path / "absolute.bin").exists()
    _receive(receiver, "kept.bin")
    assert (tmp_path / "inbox" / "kept.bin").read_bytes() == b"payload"

    host = RemoteDesktopHost(token="t", bind="127.0.0.1", port=0)
    _receive(host._ensure_file_receiver(), str(tmp_path / "host_side.bin"))
    assert (tmp_path / "host_side.bin").read_bytes() == b"payload"
