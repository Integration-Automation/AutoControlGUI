"""Stand up a remote-desktop host on one port and connect a viewer.

Both sides run in the same process for clarity. In production the host
runs on the operator's box and the viewer runs anywhere with a TCP
route. Pass ``ssl_context=`` (built with ``ssl.create_default_context``
on each side) to upgrade to TLS.
"""
import secrets
import threading
import time

import je_auto_control as ac


def main() -> None:
    token = secrets.token_urlsafe(32)
    host = ac.RemoteDesktopHost(
        token=token,
        bind="127.0.0.1",
        port=0,                # 0 → kernel picks a free port
        fps=5.0,
    )
    host.start()
    print(f"host listening on 127.0.0.1:{host.port}")

    got_frame = threading.Event()
    frame_size = 0

    def on_frame(payload: bytes) -> None:
        nonlocal frame_size
        if got_frame.is_set():
            return
        frame_size = len(payload)
        got_frame.set()

    viewer = ac.RemoteDesktopViewer(
        host="127.0.0.1",
        port=host.port,
        token=token,
        on_frame=on_frame,
    )
    viewer.connect()
    got_frame.wait(timeout=5.0)
    if got_frame.is_set():
        print(f"viewer received first frame: {frame_size} bytes")
    else:
        print("timed out waiting for first frame")

    # Let the viewer pump a couple more frames so the host's send path
    # is exercised end-to-end before we tear down.
    time.sleep(1.0)
    viewer.disconnect()
    host.stop()


if __name__ == "__main__":
    main()
