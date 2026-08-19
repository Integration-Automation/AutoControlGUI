#!/bin/sh
# Bring up a real X server with a real window manager, then run the X11
# verification inside it.
#
# The verification runs twice, over two monitor layouts:
#
#   * one monitor covering the whole screen — the single-display desktop;
#   * two monitors side by side, declared with `xrandr --setmonitor` — what
#     a dual-display desktop reports to its clients. X11 exposes that through
#     RANDR monitors rather than through separate screens, so this is the
#     shape a client actually sees.
#
# There is deliberately no negative-origin layout: on X11 the root window is
# the union of every monitor and always starts at (0, 0), so a monitor to the
# left shifts the others right instead of moving the origin. The Wayland
# job's second layout has no analogue here.
#
# Nothing below is allowed to skip quietly. If the server, the window manager
# or the monitor layout cannot be brought up, this says so and fails.
set -eu

GEOMETRY="${SCREEN_GEOMETRY:-1280x800x24}"
DISPLAY_NUM="${DISPLAY:-:99}"

echo "starting Xvfb on ${DISPLAY_NUM} at ${GEOMETRY}"
Xvfb "${DISPLAY_NUM}" -screen 0 "${GEOMETRY}" +extension RANDR \
    -nolisten tcp >/tmp/xvfb.log 2>&1 &
XVFB_PID=$!

# xdpyinfo is the server answering for itself, so it is also the readiest
# proof that the server is up — a fixed sleep would be a guess.
ready=0
for _ in $(seq 1 100); do
    if xdpyinfo >/dev/null 2>&1; then
        ready=1
        break
    fi
    if ! kill -0 "$XVFB_PID" 2>/dev/null; then
        echo "Xvfb exited before accepting a connection; its log follows:"
        cat /tmp/xvfb.log
        exit 1
    fi
    sleep 0.1
done
if [ "$ready" -ne 1 ]; then
    echo "Xvfb never accepted a connection; its log follows:"
    cat /tmp/xvfb.log
    exit 1
fi
echo "Xvfb is up"

# openbox owns _NET_* — the window-management checks read the properties it
# maintains, so a session without a window manager would test nothing.
openbox >/tmp/openbox.log 2>&1 &
OPENBOX_PID=$!
wm=0
for _ in $(seq 1 100); do
    if xprop -root _NET_SUPPORTING_WM_CHECK 2>/dev/null | grep -q window; then
        wm=1
        break
    fi
    if ! kill -0 "$OPENBOX_PID" 2>/dev/null; then
        echo "openbox exited before claiming the screen; its log follows:"
        cat /tmp/openbox.log
        exit 1
    fi
    sleep 0.1
done
if [ "$wm" -ne 1 ]; then
    echo "no window manager claimed the screen; openbox log follows:"
    cat /tmp/openbox.log
    exit 1
fi
echo "openbox is managing ${DISPLAY_NUM}"

# Runs one pass over one monitor layout; echoes the number of failed checks.
run_pass() {
    label="$1"
    echo "========================================================================"
    echo "layout: ${label}"
    echo "========================================================================"
    xrandr --listmonitors || true
    rc=0
    python3 /opt/verify/x11_verify.py || rc=$?
    return "$rc"
}

total=0

run_pass "one monitor over the whole screen" || total=$((total + $?))

# Split the same screen into two RANDR monitors. Physical size is required by
# the syntax and irrelevant here; `none` means the monitor is backed by no
# physical output, which is exactly what a virtual layout is.
echo
half_width=$(xdpyinfo | awk '/dimensions:/ {split($2, d, "x"); print int(d[1] / 2)}')
height=$(xdpyinfo | awk '/dimensions:/ {split($2, d, "x"); print d[2]}')
if ! xrandr --setmonitor AC-left "${half_width}/169x${height}/211+0+0" none \
   || ! xrandr --setmonitor AC-right \
        "${half_width}/169x${height}/211+${half_width}+0" none; then
    echo "FAILED to declare a two-monitor layout with xrandr --setmonitor."
    echo "That is a real failure, not a reason to skip: the dual-display"
    echo "geometry below is exactly what has never been checked."
    exit 1
fi

run_pass "two monitors side by side" || total=$((total + $?))

echo
echo "========================================================================"
echo "total failed checks across both layouts: ${total}"
echo "========================================================================"

kill "$OPENBOX_PID" 2>/dev/null || true
kill "$XVFB_PID" 2>/dev/null || true

exit "$total"
