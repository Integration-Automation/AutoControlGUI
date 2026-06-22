"""Headless tests for AC_wait_for_port / wait_until_port.

The TCP connector is injectable, so most cases are deterministic and need
no real socket; one case binds a real loopback listener.
"""
import socket
import threading

import pytest

import je_auto_control as ac
from je_auto_control.utils.smart_waits.waits import wait_until_port


def _connector(values):
    """Return a connector yielding ``values`` then repeating the last one."""
    seq = list(values)

    def connect(_host, _port, _timeout):
        return seq.pop(0) if len(seq) > 1 else seq[0]
    return connect


def test_succeeds_when_port_open():
    outcome = wait_until_port("localhost", 8080,
                              connector=_connector([True]))
    assert outcome.succeeded is True
    assert "open" in outcome.reason


def test_succeeds_after_port_comes_up():
    outcome = wait_until_port(
        "localhost", 9000, timeout_s=1.0, poll_interval_s=0.01,
        connector=_connector([False, False, True]))
    assert outcome.succeeded is True
    assert outcome.samples_taken >= 3


def test_times_out_when_port_closed():
    outcome = wait_until_port(
        "localhost", 9000, timeout_s=0.2, poll_interval_s=0.02,
        connector=_connector([False]))
    assert outcome.succeeded is False
    assert "timeout" in outcome.reason


@pytest.mark.parametrize("kwargs", [
    {"timeout_s": 0}, {"poll_interval_s": 0}, {"port": 0}, {"port": 70000},
])
def test_validation_errors(kwargs):
    args = {"host": "localhost", "port": 8080, "timeout_s": 10.0,
            "poll_interval_s": 0.25, "connect_timeout_s": 1.0}
    args.update(kwargs)
    with pytest.raises(ValueError):
        wait_until_port(
            args["host"], args["port"], timeout_s=args["timeout_s"],
            poll_interval_s=args["poll_interval_s"],
            connect_timeout_s=args["connect_timeout_s"],
            connector=_connector([True]))


def test_real_loopback_listener():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    accepted = []
    threading.Thread(
        target=lambda: accepted.append(server.accept()), daemon=True).start()
    try:
        outcome = wait_until_port("127.0.0.1", port, timeout_s=2.0)
        assert outcome.succeeded is True
    finally:
        server.close()


def test_facade_executor_and_mcp_wiring():
    assert ac.wait_until_port is wait_until_port
    assert "AC_wait_for_port" in ac.executor.known_commands()
    record = ac.execute_action(
        [["AC_wait_for_port", {"host": "127.0.0.1", "port": 9, "timeout_s": 0.15,
                               "poll_interval_s": 0.02, "connect_timeout_s": 0.05}]])
    # port 9 (discard) is almost certainly closed -> a timeout outcome recorded
    assert any("9" in str(value) for value in record.values())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {tool.name for tool in build_default_tool_registry()}
    assert "ac_wait_for_port" in names
