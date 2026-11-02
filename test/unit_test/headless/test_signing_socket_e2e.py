"""Enforced action signatures, end to end through the TCP socket server.

REST ``POST /execute_file`` and the MCP ``ac_execute_action_file`` tool were
driven this way already (``test_signing_passphrase_e2e.py``); the socket
server -- the third network surface that can run a file, through
``AC_execute_files`` in the action list it is sent -- was not.

Loopback only, an ephemeral port, and the real server with the real
executor: the action files hold one probe command registered for the test, so
nothing touches the mouse, keyboard or screen.
"""
import json
import socket

import pytest

from je_auto_control.utils.action_signing import (
    create_signing_keypair, sign_action_file, signer,
)
from je_auto_control.utils.action_signing.config import PASSPHRASE_ENV
from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.rbac import USERS_ENV
from je_auto_control.utils.socket_server.auto_control_socket_server import (
    start_autocontrol_socket_server,
)

pytest.importorskip("cryptography", exc_type=ImportError)

PRIVATE_ENV = "JE_AUTOCONTROL_ACTION_SIGNING_PRIVATE_KEY"
PUBLIC_ENV = "JE_AUTOCONTROL_ACTION_SIGNING_PUBLIC_KEY"
LEGACY_ENV = "JE_AUTOCONTROL_ACCEPT_LEGACY_ACTION_SIGNATURES"
REQUIRE_ENV = "JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS"
_PROBE = "AC_signed_socket_probe"
_END = "Return_Data_Over_JE"
_WAIT = 10.0
_PHRASE = "correct horse battery staple"  # NOSONAR a test passphrase for a throwaway key


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch, tmp_path):
    """No signing or RBAC variable leaks in, and the per-user HMAC key lives in tmp_path."""
    for name in (PRIVATE_ENV, PUBLIC_ENV, LEGACY_ENV, REQUIRE_ENV, PASSPHRASE_ENV, USERS_ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(signer, "_default_key_path",
                        lambda: tmp_path / "home" / "action_signing_key")


@pytest.fixture
def probe(monkeypatch):
    values = []
    monkeypatch.setitem(executor.event_dict, _PROBE,
                        lambda value=None: values.append(value) or value)
    return values


@pytest.fixture
def action_file(tmp_path):
    path = tmp_path / "flow.json"
    path.write_text(json.dumps([[_PROBE, {"value": "signed"}]]), encoding="utf-8")
    return path


@pytest.fixture
def keys(tmp_path):
    private, public = tmp_path / "signer" / "private.pem", tmp_path / "public.pem"
    create_signing_keypair(private, public, passphrase=_PHRASE)
    return private, public


@pytest.fixture
def endpoint(monkeypatch, keys):
    """An execution endpoint: signatures enforced, the public key and nothing else."""
    monkeypatch.setenv(PUBLIC_ENV, str(keys[1]))
    monkeypatch.setenv(REQUIRE_ENV, "1")
    return keys


@pytest.fixture
def server():
    running = start_autocontrol_socket_server("127.0.0.1", 0)
    yield running
    running.shutdown()
    running.server_close()


def _send(server, actions):
    """Send one command; return the reply up to the end-of-reply marker."""
    with socket.create_connection(server.server_address[:2], timeout=_WAIT) as connection:
        connection.sendall((json.dumps(actions) + "\n").encode("utf-8"))
        reply = b""
        while _END.encode("utf-8") not in reply:
            chunk = connection.recv(65536)
            if not chunk:
                break
            reply += chunk
    text = reply.decode("utf-8")
    assert _END in text, "the server always ends its answer with the marker"
    return text.split(_END)[0]


def _run_file(server, path):
    return _send(server, [["AC_execute_files", {"execute_files_list": [str(path)]}]])


def _sign(keys, path):
    """What the signing machine does; it is the only place the private key is."""
    return sign_action_file(path, private_key_path=keys[0], passphrase=_PHRASE)


def test_the_socket_server_runs_a_signed_file_and_refuses_the_rest(
        server, endpoint, action_file, probe):
    reply = _run_file(server, action_file)
    assert "missing signature sidecar" in reply
    assert probe == []
    _sign(endpoint, action_file)
    reply = _run_file(server, action_file)
    assert probe == ["signed"]
    assert "signature" not in reply
    action_file.write_text(json.dumps([[_PROBE, {"value": "tampered"}]]), encoding="utf-8")
    reply = _run_file(server, action_file)
    assert "signature mismatch" in reply
    assert probe == ["signed"], "the tampered file did not run"


def test_the_socket_server_refuses_another_key_and_an_hmac_sidecar(
        server, endpoint, action_file, probe, tmp_path, monkeypatch):
    # Both sidecars are written "elsewhere": this endpoint refuses to make either.
    monkeypatch.delenv(PUBLIC_ENV)
    other_private = tmp_path / "other.pem"
    create_signing_keypair(other_private, tmp_path / "other.pub")
    sign_action_file(action_file, private_key_path=other_private)
    monkeypatch.setenv(PUBLIC_ENV, str(endpoint[1]))
    assert "different key" in _run_file(server, action_file)
    # An HMAC sidecar, which anyone able to execute could have written.
    monkeypatch.delenv(PUBLIC_ENV)
    sign_action_file(action_file, key="shared-value")
    monkeypatch.setenv(PUBLIC_ENV, str(endpoint[1]))
    assert "legacy HMAC signature refused" in _run_file(server, action_file)
    assert probe == []


def test_a_socket_client_cannot_sign_on_an_execution_endpoint(
        server, endpoint, action_file, probe):
    reply = _send(server, [["AC_sign_action_file", {"path": str(action_file)}]])
    assert "verifies only" in reply
    assert not action_file.with_name("flow.json.sig").exists()
    assert "missing signature sidecar" in _run_file(server, action_file)
    assert probe == []


def test_one_refused_file_does_not_stop_the_actions_around_it(
        server, endpoint, action_file, probe, tmp_path):
    """The refusal is that step's result; the command still answers every step."""
    signed = tmp_path / "signed.json"
    signed.write_text(json.dumps([[_PROBE, {"value": "ok"}]]), encoding="utf-8")
    _sign(endpoint, signed)
    reply = _send(server, [
        ["AC_execute_files", {"execute_files_list": [str(action_file)]}],
        ["AC_execute_files", {"execute_files_list": [str(signed)]}],
        [_PROBE, {"value": "inline"}],
    ])
    assert probe == ["ok", "inline"], "inline actions are not files and need no signature"
    assert "missing signature sidecar" in reply.splitlines()[0]


def test_without_enforcement_the_socket_server_is_unchanged(server, action_file, probe):
    reply = _run_file(server, action_file)
    assert probe == ["signed"]
    assert "signature" not in reply
