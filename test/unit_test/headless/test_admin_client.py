"""Tests for the multi-host admin console (round 24)."""
import pytest

from je_auto_control.utils.admin.admin_client import (
    AdminConsoleClient, AdminHost, default_admin_console,
)
from je_auto_control.utils.rest_api.rest_server import RestApiServer


@pytest.fixture()
def two_servers():
    a = RestApiServer(host="127.0.0.1", port=0, enable_audit=False)
    b = RestApiServer(host="127.0.0.1", port=0, enable_audit=False)
    a.start()
    b.start()
    try:
        yield a, b
    finally:
        a.stop(timeout=1.0)
        b.stop(timeout=1.0)


@pytest.fixture()
def client(tmp_path):
    return AdminConsoleClient(persist_path=tmp_path / "hosts.json")


def _url(server):
    # Tests run against a stub localhost HTTP server fixture; TLS
    # would force every test to mint certs without real coverage gain.
    host, port = server.address
    return f"http://{host}:{port}"  # NOSONAR — loopback test fixture URL only


def test_add_host_round_trip(client, two_servers):
    a, _ = two_servers
    host = client.add_host(label="alpha", base_url=_url(a), token=a.token)
    assert isinstance(host, AdminHost)
    assert host.label == "alpha"
    assert client.list_hosts()[0].label == "alpha"


def test_add_host_validates_required_fields(client):
    # The "http://x" literals below are placeholder URL strings passed
    # to a validator that only checks emptiness; no traffic is ever
    # sent to them.
    with pytest.raises(ValueError):
        client.add_host(label="", base_url="http://x", token="t")  # NOSONAR — validator-only placeholder
    with pytest.raises(ValueError):
        client.add_host(label="a", base_url="", token="t")
    with pytest.raises(ValueError):
        client.add_host(label="a", base_url="http://x", token="")  # NOSONAR — validator-only placeholder


def test_remove_host(client, two_servers):
    a, _ = two_servers
    client.add_host(label="alpha", base_url=_url(a), token=a.token)
    assert client.remove_host("alpha") is True
    assert client.remove_host("alpha") is False
    assert client.list_hosts() == []


def test_persistence_round_trip(tmp_path, two_servers):
    a, b = two_servers
    path = tmp_path / "hosts.json"
    client = AdminConsoleClient(persist_path=path)
    client.add_host(label="alpha", base_url=_url(a), token=a.token,
                    tags=["lab"])
    client.add_host(label="beta", base_url=_url(b), token=b.token)

    reloaded = AdminConsoleClient(persist_path=path)
    labels = sorted(h.label for h in reloaded.list_hosts())
    assert labels == ["alpha", "beta"]
    alpha = next(h for h in reloaded.list_hosts() if h.label == "alpha")
    assert alpha.tags == ["lab"]


def test_parallel_poll_marks_both_healthy(client, two_servers):
    a, b = two_servers
    client.add_host(label="alpha", base_url=_url(a), token=a.token)
    client.add_host(label="beta", base_url=_url(b), token=b.token)
    statuses = client.poll_all()
    assert {s.label for s in statuses} == {"alpha", "beta"}
    assert all(s.healthy for s in statuses), statuses


def test_bad_token_marks_host_unhealthy(client, two_servers):
    a, _ = two_servers
    client.add_host(label="bad", base_url=_url(a), token="not-the-token")
    status = client.poll_all(labels=["bad"])[0]
    assert status.healthy is False
    assert status.error is not None and "401" in status.error


def test_broadcast_execute_runs_on_all_hosts(client, two_servers):
    a, b = two_servers
    client.add_host(label="alpha", base_url=_url(a), token=a.token)
    client.add_host(label="beta", base_url=_url(b), token=b.token)
    results = client.broadcast_execute(actions=[["AC_get_mouse_table"]])
    assert {r["label"] for r in results} == {"alpha", "beta"}
    assert all(r["ok"] for r in results), results


def test_broadcast_execute_reports_per_host_failure(client, two_servers):
    a, _ = two_servers
    client.add_host(label="alpha", base_url=_url(a), token=a.token)
    client.add_host(label="bad", base_url=_url(a), token="wrong")
    results = client.broadcast_execute(actions=[["AC_get_mouse_table"]])
    by_label = {r["label"]: r for r in results}
    assert by_label["alpha"]["ok"] is True
    assert by_label["bad"]["ok"] is False


def test_default_admin_console_is_singleton():
    a = default_admin_console()
    b = default_admin_console()
    assert a is b
