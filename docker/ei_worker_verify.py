"""Verify process-owned EI input, EOF cleanup, failure isolation and IPC latency."""
from __future__ import annotations

import faulthandler
import json
import os
from pathlib import Path
import signal
import socket
import statistics
import tempfile
import threading
import time

from eis_server import RecordingEisServer
from eis_verify import _require, _wait_for, check, _results
from je_auto_control.linux_wayland.ei_transport import EiWorkerClient, EiWorkerError, InputEvent


def _live_peer() -> str:
    with tempfile.TemporaryDirectory(prefix="ei-worker-live-") as directory:
        path = str(Path(directory, "eis"))
        server = RecordingEisServer(path)
        server.start()
        client = EiWorkerClient()
        try:
            client.connect(timeout=10, socket_path=path.encode())
            ack = client.send([
                InputEvent("press_key", (29,)), InputEvent("release_key", (29,)),
                InputEvent("press_button", (272,)), InputEvent("release_button", (272,)),
                InputEvent("set_position", (640, 400)), InputEvent("scroll", (0, -1)),
            ], timeout_s=3)
            _require(ack.applied == 6, "incomplete input acknowledgement")
            _wait_for(lambda: len(server.recording.keys) >= 2 and len(server.recording.scrolls) >= 1,
                      3, "worker inputs on the real EIS wire")
            _require(server.recording.keys[:2] == [(29, True), (29, False)], "worker changed keyboard input")
            _require(server.recording.absolute_motions[-1] == (640, 400), "worker changed coordinates")
            _require(server.recording.buttons[:2] == [(272, True), (272, False)], "worker changed buttons")
            _require(server.recording.scrolls[-1] == (0, -120), "worker changed scroll units")
            samples = []
            for _ in range(50):
                started = time.monotonic()
                client.check_permission()
                samples.append((time.monotonic() - started) * 1000)
            metrics = {"ipc_roundtrip_ms_p50": statistics.median(samples),
                       "ipc_roundtrip_ms_p95": sorted(samples)[47], "samples": len(samples)}
            client.press_key(42)
            client.close()
            _wait_for(lambda: (42, False) in server.recording.keys, 3, "EOF releases held Shift")
            _require(not client.worker_running and not client.open_channel, "worker resources still owned")
            _require(client.worker_exit_code == 0, f"worker exit {client.worker_exit_code}: {client.crash_details}")
            _require(server.error is None, f"EIS serving failed: {server.error}")
            return json.dumps(metrics, sort_keys=True)
        finally:
            client.close()
            server.stop()


def _half_open() -> str:
    baseline = len(os.listdir("/proc/self/fd"))
    for _ in range(3):
        with tempfile.TemporaryDirectory(prefix="ei-worker-half-open-") as directory:
            reached = threading.Event()
            stop = threading.Event()
            with socket.socket(socket.AF_UNIX) as listener:
                path = str(Path(directory, "eis"))
                listener.bind(path)
                listener.listen(1)
                listener.settimeout(5)

                def accept():
                    with listener.accept()[0]:
                        reached.set()
                        stop.wait(5)

                thread = threading.Thread(target=accept)
                thread.start()
                client = EiWorkerClient()
                try:
                    try:
                        client.connect(timeout=3, socket_path=path.encode())
                    except EiWorkerError:
                        pass
                    else:
                        raise AssertionError("half-open peer unexpectedly authorized input")
                    _require(reached.is_set(), "probe never reached half-open native connection")
                    _require(not client.worker_running and not client.open_channel, "half-open helper survived")
                finally:
                    client.close()
                    stop.set()
                    thread.join(timeout=6)
                _require(not thread.is_alive(), "half-open serving thread survived")
    after = len(os.listdir("/proc/self/fd"))
    _require(after == baseline, f"parent fd leak: {baseline} -> {after}")
    return f"three half-open failures; parent fd count {baseline} -> {after}"


def _crash() -> str:
    with tempfile.TemporaryDirectory(prefix="ei-worker-crash-") as directory:
        path = str(Path(directory, "eis"))
        server = RecordingEisServer(path)
        server.start()
        client = EiWorkerClient()
        try:
            client.connect(timeout=10, socket_path=path.encode())
            client.press_key(29)
            process = client._resources.process
            _require(process is not None, "no worker process")
            os.kill(process.pid, signal.SIGABRT)
            process.wait(timeout=5)
            try:
                client.release_key(29)
            except EiWorkerError:
                pass
            else:
                raise AssertionError("crashed worker accepted another input")
            _require(not client.worker_running and not client.open_channel, "crashed worker not reaped")
            _require(client.worker_exit_code == -signal.SIGABRT, "crash signal not preserved")
            _require("Fatal Python error" in client.crash_details, "faulthandler crash evidence is missing")
            _wait_for(lambda: server.recording.disconnects >= 1, 3, "EIS client disconnect after crash")
            print(client.crash_details)
            return "parent survived; child signal and stack retained; EIS connection revoked"
        finally:
            client.close()
            server.stop()


def main() -> int:
    """Run native checks without a desktop or a portal consent dialog."""
    faulthandler.enable()
    check("process-owned handshake, emission, held-key cleanup and IPC latency", _live_peer)
    check("half-open helper exits reclaim descriptors on every explicit retry", _half_open)
    check("native worker crash leaves parent alive and retains crash evidence", _crash)
    return sum(not success for _, success in _results)


if __name__ == "__main__":
    raise SystemExit(main())
