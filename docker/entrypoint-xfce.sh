#!/bin/sh
# AutoControl XFCE container entrypoint — starts Xvfb + XFCE session +
# x11vnc, then the requested host process.
#
# Modes are identical to the slim entrypoint: rest | remote-host |
# signaling | shell. Any extra args are forwarded.

set -eu

GEOMETRY="${XVFB_GEOMETRY:-1280x800x24}"
DISPLAY_NUM="${DISPLAY:-:99}"
VNC_PORT="${AUTOCONTROL_VNC_PORT:-5900}"
VNC_PASSWORD="${AUTOCONTROL_VNC_PASSWORD:-}"

# 1) Headless X server.
Xvfb "$DISPLAY_NUM" -screen 0 "$GEOMETRY" -nolisten tcp &
XVFB_PID=$!
sleep 0.5

# 2) XFCE desktop session, on the same display.
DISPLAY="$DISPLAY_NUM" startxfce4 >/tmp/xfce.log 2>&1 &
XFCE_PID=$!
sleep 1

# 3) VNC server so an operator can attach with any viewer.
VNC_ARGS="-display $DISPLAY_NUM -nopw -listen 0.0.0.0 -rfbport $VNC_PORT -forever -shared -quiet"
if [ -n "$VNC_PASSWORD" ]; then
    echo "$VNC_PASSWORD" | x11vnc -storepasswd - /tmp/.vncpasswd
    VNC_ARGS="-display $DISPLAY_NUM -rfbauth /tmp/.vncpasswd -listen 0.0.0.0 -rfbport $VNC_PORT -forever -shared -quiet"
fi
x11vnc $VNC_ARGS &
VNC_PID=$!

cleanup() {
    for pid in "$VNC_PID" "$XFCE_PID" "$XVFB_PID"; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
        fi
    done
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
        exec /bin/bash "$@"
        ;;
    *)
        echo "unknown mode: $MODE (expected rest|remote-host|signaling|shell)" >&2
        exit 2
        ;;
esac
