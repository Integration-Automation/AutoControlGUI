"""A remote action failure is reported as a failure, not as HTTP 200 success.

REST ``/execute`` ran with ``raise_on_error=False`` and answered 200 with the
failure buried in ``result``, so the admin console's ``ok`` meant only "the
host answered" and a DAG remote node whose actions all failed counted as
succeeded. ``raise_on_error`` is opt-in on the wire (other tools call
``/execute``); the admin client, the DAG runner and the Admin Console send it.
"""
import types

import pytest


def _ctx(body):
    return types.SimpleNamespace(body=body, query={}, headers={}, path="/execute")


def test_strict_execute_reports_the_first_failure():
    from je_auto_control.utils.rest_api.rest_handlers import handle_execute
    status, body = handle_execute(_ctx({"actions": [["AC_sleep", {}]], "raise_on_error": True}))
    assert status == 200 and body["ok"] is False
    assert "KeyError" in body["error"]
    status, body = handle_execute(_ctx({"actions": [["AC_sleep", {"seconds": 0}]],
                                        "raise_on_error": True}))
    assert status == 200 and body["ok"] is True and "result" in body


def test_the_default_execute_is_unchanged_and_the_flag_is_validated():
    from je_auto_control.utils.rest_api.rest_handlers import handle_execute
    status, body = handle_execute(_ctx({"actions": [["AC_sleep", {}]]}))
    assert status == 200 and "ok" not in body
    assert any("KeyError" in str(value) for value in body["result"].values())
    status, _body = handle_execute(_ctx({"actions": [], "raise_on_error": "yes"}))
    assert status == 400


@pytest.fixture
def client(tmp_path):
    from je_auto_control.utils.admin.admin_client import AdminConsoleClient
    console = AdminConsoleClient(persist_path=tmp_path / "hosts.json")
    console.add_host("lab", "http://lab.example", "tok")  # NOSONAR python:S5332  # reason: test fixture, no network
    return console


def test_the_admin_client_turns_a_remote_failure_into_ok_false(client, monkeypatch):
    sent = []

    def post(_host, path, body):
        sent.append((path, body))
        return {"ok": False, "error": "KeyError: 'seconds'"}

    monkeypatch.setattr(client, "_http_post", post)
    (row,) = client.broadcast_execute([["AC_sleep", {}]], raise_on_error=True)
    assert row["ok"] is False and row["error"] == "KeyError: 'seconds'"
    assert sent == [("/execute", {"actions": [["AC_sleep", {}]], "raise_on_error": True})]


def test_the_default_broadcast_sends_the_old_body(client, monkeypatch):
    sent = []
    monkeypatch.setattr(client, "_http_post",
                        lambda _h, path, body: sent.append(body) or {"result": {}})
    (row,) = client.broadcast_execute([["AC_x"]])
    assert row["ok"] is True and sent == [{"actions": [["AC_x"]]}]


def test_a_dag_remote_node_fails_when_its_actions_fail(monkeypatch):
    from je_auto_control.utils.admin import admin_client
    from je_auto_control.utils.dag import runner
    calls = []

    class _Console:
        def broadcast_execute(self, actions, labels, raise_on_error=False):
            calls.append(raise_on_error)
            return [{"label": labels[0], "ok": False, "error": "KeyError: 'seconds'"}]

    monkeypatch.setattr(admin_client, "default_admin_console", _Console)
    node = types.SimpleNamespace(host="lab", actions=[["AC_sleep", {}]], action_file=None, id="n")
    with pytest.raises(RuntimeError, match="seconds"):
        runner._default_remote_runner(node, None)  # noqa: SLF001
    assert calls == [True]
