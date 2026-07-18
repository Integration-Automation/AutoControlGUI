"""Audit round 3 regression for the relay pipe (finding 4).

When one side of a paired session EOFs, the opposite pipe thread is parked in a
blocking recv(); the ``stop`` flag alone cannot wake it. The fix shuts the
opposite socket down so both threads exit and both sockets are closed instead
of hanging join() forever.
"""
import socket
import threading

from je_auto_control.utils.remote_desktop.relay import _pair_and_pump


def test_pair_and_pump_exits_when_one_side_closes():
    host_a, host_b = socket.socketpair()
    viewer_a, viewer_b = socket.socketpair()
    done = threading.Event()

    def _run() -> None:
        _pair_and_pump(host_b, viewer_b)
        done.set()

    threading.Thread(target=_run, daemon=True).start()

    # The host peer disconnects while the viewer side sits idle (parked in
    # recv). Pre-fix, the viewer->host pipe thread never wakes and
    # _pair_and_pump's join() blocks forever, so done is never set.
    host_a.close()

    assert done.wait(timeout=3.0), "_pair_and_pump hung after one side EOF"
    assert host_b.fileno() == -1
    assert viewer_b.fileno() == -1

    for extra in (host_a, viewer_a):
        try:
            extra.close()
        except OSError:
            pass
