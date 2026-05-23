#!/bin/sh
# AutoControl container entrypoint — starts Xvfb then the requested host
# process. The first argument selects the mode:
#
#   rest           — start the REST API (default; reuses AC_rest_api_start)
#   remote-host    — start the Remote Desktop TCP host
#   signaling      — start the WebRTC signaling server
#   shell          — drop into bash for debugging
#
# Any further args after the mode are forwarded to the underlying tool.

set -eu

# 1280x800x24 matches a typical laptop and is small enough to JPEG-encode
# cheaply. Override via XVFB_GEOMETRY env if you need a different size.
GEOMETRY="${XVFB_GEOMETRY:-1280x800x24}"
DISPLAY_NUM="${DISPLAY:-:99}"

# Launch Xvfb in the background. Use -nolisten tcp so the X server stays
# unreachable from outside the container; the only consumer is the
# AutoControl host process running inside.
Xvfb "$DISPLAY_NUM" -screen 0 "$GEOMETRY" -nolisten tcp &
XVFB_PID=$!

# Give Xvfb a moment to bind the socket before any client starts.
sleep 0.5

cleanup() {
    if kill -0 "$XVFB_PID" 2>/dev/null; then
        kill "$XVFB_PID" 2>/dev/null || true
        wait "$XVFB_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

MODE="${1:-rest}"
shift 2>/dev/null || true

case "$MODE" in
    rest)
        exec python -m je_auto_control.utils.rest_api.rest_server \
            --host 0.0.0.0 --port 9939 "$@"
        ;;
    remote-host)
        exec python -c "import os, time; \
from je_auto_control.utils.remote_desktop import RemoteDesktopHost; \
h = RemoteDesktopHost(token=os.environ.get('AC_TOKEN', 'change-me'), \
                      bind='0.0.0.0', port=int(os.environ.get('AC_PORT', '9940'))); \
h.start(); \
print('listening on', h.port); \
[time.sleep(60) for _ in iter(int, 1)]"
        ;;
    signaling)
        exec python -m je_auto_control.utils.remote_desktop.signaling_server \
            --host 0.0.0.0 --port 8765 "$@"
        ;;
    shell)
        exec /bin/sh "$@"
        ;;
    *)
        echo "unknown mode: $MODE (expected rest|remote-host|signaling|shell)" >&2
        exit 2
        ;;
esac
