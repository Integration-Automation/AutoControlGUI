"""A passphrase for the Ed25519 private key, and enforced signatures end to end.

The private key was plain PEM: whoever copied the file could sign. It can
now be created with a passphrase, which the signer supplies as an argument or
through ``JE_AUTOCONTROL_ACTION_SIGNING_PASSPHRASE``; a key created without
one loads as before.

Enforced signatures were only exercised on the shared reader. Here they are
driven through the two network surfaces that run a file -- REST
``POST /execute_file`` and the MCP ``ac_execute_action_file`` tool -- over
loopback, with an execution endpoint that holds the public key only.

Nothing here touches the real mouse, keyboard or screen: the action files
hold one probe command registered for the test.
"""
import json
import logging
import urllib.error
import urllib.request

import pytest

from je_auto_control.utils.action_signing import (
    create_signing_keypair, sign_action_file, signer, verify_action_file,
)
from je_auto_control.utils.action_signing.config import PASSPHRASE_ENV
from je_auto_control.utils.exception.exceptions import (
    AutoControlException, AutoControlSignatureException,
)
from je_auto_control.utils.executor.action_executor import execute_action, executor
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.mcp_server.http_transport import DEFAULT_PATH, HttpMCPServer
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
from je_auto_control.utils.rbac import USERS_ENV
from je_auto_control.utils.rest_api.rest_server import RestApiServer

pytest.importorskip("cryptography", exc_type=ImportError)

PRIVATE_ENV = "JE_AUTOCONTROL_ACTION_SIGNING_PRIVATE_KEY"
PUBLIC_ENV = "JE_AUTOCONTROL_ACTION_SIGNING_PUBLIC_KEY"
LEGACY_ENV = "JE_AUTOCONTROL_ACCEPT_LEGACY_ACTION_SIGNATURES"
REQUIRE_ENV = "JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS"
_SCHEME = "http"  # NOSONAR localhost-only ephemeral test server; TLS out of scope
_PROBE = "AC_signed_probe"
_SECRET = "correct horse battery staple"  # NOSONAR a test passphrase for a throwaway key


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch, tmp_path):
    """No signing or RBAC variable leaks in, and the per-user HMAC key lives in tmp_path."""
    for name in (PRIVATE_ENV, PUBLIC_ENV, LEGACY_ENV, REQUIRE_ENV, PASSPHRASE_ENV, USERS_ENV,
                 "JE_AUTOCONTROL_MCP_TOKEN", "JE_AUTOCONTROL_MCP_PATH_ROOTS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(signer, "_default_key_path",
                        lambda: tmp_path / "home" / "action_signing_key")


@pytest.fixture()
def action_file(tmp_path):
    path = tmp_path / "flow.json"
    path.write_text(json.dumps([[_PROBE, {"value": "signed"}]]), encoding="utf-8")
    return path


# --- the passphrase ---------------------------------------------------------

@pytest.fixture()
def locked_keys(tmp_path):
    private, public = tmp_path / "signer" / "private.pem", tmp_path / "public.pem"
    create_signing_keypair(private, public, passphrase=_SECRET)
    return private, public


def test_a_passphrase_encrypts_the_private_key_file(locked_keys, tmp_path):
    private, _public = locked_keys
    assert b"ENCRYPTED PRIVATE KEY" in private.read_bytes()
    plain = tmp_path / "plain.pem"
    create_signing_keypair(plain, tmp_path / "plain.pub")
    assert b"ENCRYPTED" not in plain.read_bytes()
    empty = tmp_path / "empty.pem"
    create_signing_keypair(empty, tmp_path / "empty.pub", passphrase="")
    assert b"ENCRYPTED" not in empty.read_bytes(), "an empty passphrase is no passphrase"


def test_signing_with_a_locked_key_needs_the_passphrase(locked_keys, action_file):
    private, public = locked_keys
    with pytest.raises(AutoControlException, match=PASSPHRASE_ENV):
        sign_action_file(action_file, private_key_path=private)
    with pytest.raises(AutoControlException, match="wrong passphrase"):
        sign_action_file(action_file, private_key_path=private, passphrase="nope")
    assert not action_file.with_name("flow.json.sig").exists()
    sign_action_file(action_file, private_key_path=private, passphrase=_SECRET)
    assert verify_action_file(action_file, public_key_path=public).verified


def test_the_signer_reads_the_passphrase_from_the_environment(
        locked_keys, action_file, monkeypatch):
    private, public = locked_keys
    monkeypatch.setenv(PRIVATE_ENV, str(private))
    monkeypatch.setenv(PASSPHRASE_ENV, _SECRET)
    sign_action_file(action_file)
    assert verify_action_file(action_file, public_key_path=public).verified
    # A signing machine verifies with the key it derives from its private half.
    assert verify_action_file(action_file).verified


def test_bytes_and_text_passphrases_are_the_same(locked_keys, action_file):
    private, public = locked_keys
    sign_action_file(action_file, private_key_path=private, passphrase=_SECRET.encode("utf-8"))
    assert verify_action_file(action_file, public_key_path=public).verified


def test_an_unencrypted_key_still_loads_even_with_a_passphrase_around(
        tmp_path, action_file, monkeypatch):
    private, public = tmp_path / "private.pem", tmp_path / "public.pem"
    create_signing_keypair(private, public)
    sign_action_file(action_file, private_key_path=private)
    assert verify_action_file(action_file, public_key_path=public).verified
    monkeypatch.setenv(PASSPHRASE_ENV, _SECRET)
    sign_action_file(action_file, private_key_path=private)
    sign_action_file(action_file, private_key_path=private, passphrase="anything")
    assert verify_action_file(action_file, public_key_path=public).verified


def test_the_commands_take_a_passphrase_and_it_is_not_logged(tmp_path, action_file, caplog):
    private, public = tmp_path / "k" / "private.pem", tmp_path / "k" / "public.pem"
    private.parent.mkdir()
    autocontrol_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.DEBUG, logger=autocontrol_logger.name):
            record = execute_action([
                ["AC_create_signing_keypair", {"private_path": str(private),
                                               "public_path": str(public),
                                               "passphrase": _SECRET}],
                ["AC_sign_action_file", {"path": str(action_file),
                                         "private_key_path": str(private),
                                         "passphrase": _SECRET}],
                ["AC_sign_action_file", {"path": str(action_file),
                                         "private_key_path": str(private)}],
            ])
    finally:
        autocontrol_logger.removeHandler(caplog.handler)
    created, signed, refused = record.values()
    assert created == {"private_path": str(private), "public_path": str(public)}
    assert signed == {"signature_path": str(action_file) + ".sig"}
    assert PASSPHRASE_ENV in str(refused)
    assert b"ENCRYPTED" in private.read_bytes()
    assert verify_action_file(action_file, public_key_path=public).verified
    assert _SECRET not in "\n".join(entry.getMessage() for entry in caplog.records)


# --- enforced signatures, end to end ----------------------------------------

@pytest.fixture()
def probe(monkeypatch):
    values = []
    monkeypatch.setitem(executor.event_dict, _PROBE,
                        lambda value=None: values.append(value) or value)
    return values


@pytest.fixture()
def endpoint(monkeypatch, locked_keys):
    """An execution endpoint: signatures enforced, the public key and nothing else."""
    monkeypatch.setenv(PUBLIC_ENV, str(locked_keys[1]))
    monkeypatch.setenv(REQUIRE_ENV, "1")
    return locked_keys


def _sign(endpoint, path):
    """What the signing machine does; it is the only place the private key is."""
    return sign_action_file(path, private_key_path=endpoint[0], passphrase=_SECRET)


def _post(server, path, body, token=None, headers=None):
    host, port = server.address
    request = urllib.request.Request(
        f"{_SCHEME}://{host}:{port}{path}", data=json.dumps(body).encode("utf-8"),
        method="POST", headers={"Content-Type": "application/json", **(headers or {})})
    if token is not None:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # nosec B310  # reason: loopback test server
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


@pytest.fixture()
def rest():
    server = RestApiServer(host="127.0.0.1", port=0, token="rest-token", enable_audit=False)
    server.start()
    yield server
    server.stop(timeout=1.0)


def _rest_run(server, path):
    return _post(server, "/execute_file", {"path": str(path)}, token="rest-token")


def test_rest_execute_file_runs_a_signed_file_and_refuses_the_rest(
        rest, endpoint, action_file, probe, tmp_path):
    status, body = _rest_run(rest, action_file)
    assert status == 403 and "missing signature sidecar" in body["error"]
    _sign(endpoint, action_file)
    status, body = _rest_run(rest, action_file)
    assert status == 200 and probe == ["signed"]
    action_file.write_text(json.dumps([[_PROBE, {"value": "tampered"}]]), encoding="utf-8")
    status, body = _rest_run(rest, action_file)
    assert status == 403 and "signature mismatch" in body["error"]
    assert probe == ["signed"], "the tampered file did not run"


def test_rest_execute_file_refuses_another_key_and_an_hmac_sidecar(
        rest, endpoint, action_file, probe, tmp_path, monkeypatch):
    # Both sidecars are written "elsewhere": this endpoint refuses to make either.
    monkeypatch.delenv(PUBLIC_ENV)
    other_private = tmp_path / "other.pem"
    create_signing_keypair(other_private, tmp_path / "other.pub")
    sign_action_file(action_file, private_key_path=other_private)
    monkeypatch.setenv(PUBLIC_ENV, str(endpoint[1]))
    status, body = _rest_run(rest, action_file)
    assert status == 403 and "different key" in body["error"]
    # An HMAC sidecar, which anyone able to execute could have written.
    monkeypatch.delenv(PUBLIC_ENV)
    sign_action_file(action_file, key="shared-secret")
    monkeypatch.setenv(PUBLIC_ENV, str(endpoint[1]))
    status, body = _rest_run(rest, action_file)
    assert status == 403 and "legacy HMAC signature refused" in body["error"]
    assert probe == []


def test_rest_cannot_sign_on_an_execution_endpoint(rest, endpoint, action_file, probe):
    status, body = _post(rest, "/execute", {"actions": [
        ["AC_sign_action_file", {"path": str(action_file)}]]}, token="rest-token")
    assert status == 200
    assert "verifies only" in str(list(body["result"].values())[0])
    assert not action_file.with_name("flow.json.sig").exists()
    assert _rest_run(rest, action_file)[0] == 403 and probe == []


def test_rest_execute_file_without_enforcement_is_unchanged(rest, action_file, probe):
    assert _rest_run(rest, action_file)[0] == 200
    assert probe == ["signed"]


@pytest.fixture()
def mcp():
    tools = [tool for tool in build_default_tool_registry(read_only=False, aliases=False)
             if tool.name == "ac_execute_action_file"]
    server = HttpMCPServer(mcp=MCPServer(tools=tools), host="127.0.0.1", port=0)
    server.start()
    yield server
    server.stop(timeout=1.0)


def _mcp_run(server, path):
    _status, body = _post(server, DEFAULT_PATH, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "ac_execute_action_file", "arguments": {"file_path": str(path)}}})
    result = body["result"]
    return result["isError"], result["content"][0]["text"]


def test_mcp_execute_action_file_runs_a_signed_file_and_refuses_the_rest(
        mcp, endpoint, action_file, probe):
    is_error, text = _mcp_run(mcp, action_file)
    assert is_error and "missing signature sidecar" in text
    _sign(endpoint, action_file)
    is_error, _text = _mcp_run(mcp, action_file)
    assert not is_error and probe == ["signed"]
    action_file.write_text(json.dumps([[_PROBE, {"value": "tampered"}]]), encoding="utf-8")
    is_error, text = _mcp_run(mcp, action_file)
    assert is_error and "signature mismatch" in text
    assert probe == ["signed"]


def test_the_refusal_is_a_typed_member_of_the_family(endpoint, action_file):
    from je_auto_control.utils.json.json_file import read_executable_action_json
    with pytest.raises(AutoControlSignatureException) as refused:
        read_executable_action_json(str(action_file))
    assert isinstance(refused.value, AutoControlException)
    with pytest.raises(AutoControlSignatureException):
        verify_action_file(action_file, raise_on_fail=True)
