"""Signature enforcement covers remote DAG nodes; two errors join the family.

``_resolve_remote_actions`` loaded a node's action file with a plain
``json.load``, so with ``JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS`` set an
unsigned file still ran on a remote host. ``UserAuthError`` and
``CredentialBrokerError`` derived from ``RuntimeError`` only, escaping every
``except AutoControlException`` boundary.
"""
import pytest

from je_auto_control.utils.admin import admin_client
from je_auto_control.utils.dag import runner
from je_auto_control.utils.dag.graph import DagNode
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.governance.credential_broker import CredentialBrokerError
from je_auto_control.utils.rbac.users import UserAuthError


def test_an_unsigned_file_is_not_sent_to_a_remote_host(tmp_path, monkeypatch):
    monkeypatch.setenv("JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS", "1")
    script = tmp_path / "unsigned.json"
    script.write_text('[["AC_type_keyboard", {"keycode": "a"}]]', encoding="utf-8")
    sent = []

    class _Console:
        def broadcast_execute(self, actions, labels):
            sent.append((actions, labels))
            return [{"ok": True, "result": "ran"}]

    monkeypatch.setattr(admin_client, "default_admin_console", lambda: _Console())
    with pytest.raises(AutoControlException):
        runner._default_remote_runner(DagNode(id="n", host="remote-1", action_file=str(script)), None)
    assert sent == []


def test_a_remote_file_still_loads_without_enforcement(tmp_path, monkeypatch):
    monkeypatch.delenv("JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS", raising=False)
    script = tmp_path / "plain.json"
    script.write_text('[["AC_type_keyboard", {"keycode": "a"}]]', encoding="utf-8")
    node = DagNode(id="n", host="remote-1", action_file=str(script))
    assert runner._resolve_remote_actions(node) == [["AC_type_keyboard", {"keycode": "a"}]]


@pytest.mark.parametrize("error_type", [UserAuthError, CredentialBrokerError])
def test_the_errors_are_in_the_framework_family(error_type):
    assert issubclass(error_type, AutoControlException)
    assert issubclass(error_type, RuntimeError)
