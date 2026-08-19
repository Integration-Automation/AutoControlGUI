#!/bin/sh
# Bring up a wlroots session that really consumes the ydotool device, and ask
# it where an absolute move lands.
#
# Three things have to be true before the question can even be asked, and each
# was once the reason this was recorded as needing a VM:
#
#   * the compositor must run libinput. WLR_BACKENDS=headless,libinput keeps
#     the outputs virtual — no GPU, no DRM — while the input half is the real
#     libinput backend rather than nothing at all.
#   * libinput must be allowed to open the device. libseat's builtin backend
#     does that without logind, but it also tries to take over a VT; a
#     container has none, and SEATD_VTBOUND=0 is what stops it trying.
#   * udev must know the device. ydotoold's uinput node is published by the
#     kernel, but libinput enumerates through udev, so udevd has to be running
#     when the device appears. It is started first for that reason.
#
# The device node itself is created here: udevd inside a container does not
# get to populate /dev, so the minor number is computed from sysfs the same
# way docker/ydotool_verify.py does it.
#
# The verification runs twice, over the same two layouts as
# docker/entrypoint-wayland.sh — side by side from the origin, and with
# HEADLESS-1 moved to x=-1280. The second is the one that separates "the
# layout corner" from "layout (0, 0)"; the first is the control where the two
# coincide and every check has to pass anyway.
set -eu

RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/xdg}"
mkdir -p "$RUNTIME_DIR" /run/udev
chmod 700 "$RUNTIME_DIR"

LOG=/tmp/verify.log
RC=/tmp/verify.rc
SWAY_LOG=/tmp/sway.log

echo "starting systemd-udevd"
/usr/lib/systemd/systemd-udevd --daemon
sleep 1

echo "starting ydotoold"
ydotoold --socket-path="$YDOTOOL_SOCKET" --socket-own="$(id -u):$(id -g)" \
    >/tmp/ydotoold.log 2>&1 &
sleep 3

# Input event nodes are character major 13, minor 64 + N.
mkdir -p /dev/input
for sysfs in /sys/class/input/event*; do
    [ -e "$sysfs" ] || continue
    node=$(basename "$sysfs")
    [ -e "/dev/input/$node" ] || \
        mknod "/dev/input/$node" c 13 $((64 + ${node#event}))
done

if [ -z "$(ls -A /dev/input 2>/dev/null)" ]; then
    echo "No input device appeared. ydotoold could not create one:"
    cat /tmp/ydotoold.log
    echo "The container needs --device /dev/uinput and"
    echo "--device-cgroup-rule 'c 13:* rmw', and the host needs the uinput"
    echo "module loaded."
    exit 1
fi
ls -l /dev/input

if ! libinput list-devices | grep -qi ydotool; then
    echo "libinput cannot see the ydotool device, so sway will not either:"
    libinput list-devices || true
    exit 1
fi

# Both outputs carry a flat colour so that anything else in a capture is the
# cursor. The values are mirrored in seat_verify.py as OUTPUT_COLOURS.
cat > /tmp/sway.cfg.in <<'SWAYCFG'
default_border none
output HEADLESS-1 position @POS1@ bg #123456 solid_color
output HEADLESS-2 position 0 0 bg #abcdef solid_color
exec sh -c 'python3 /opt/verify/seat_verify.py >/tmp/verify.log 2>&1; echo $? >/tmp/verify.rc; swaymsg exit'
SWAYCFG

# Runs one sway session over one layout; echoes the number of failed checks.
run_session() {
    label="$1"
    position="$2"
    rm -f "$LOG" "$RC" "$SWAY_LOG"
    sed "s/@POS1@/$position/" /tmp/sway.cfg.in > /tmp/sway.cfg

    echo "========================================================================"
    echo "layout: $label  (HEADLESS-1 at $position)"
    echo "========================================================================"

    if ! sway -c /tmp/sway.cfg >"$SWAY_LOG" 2>&1; then
        echo "sway exited non-zero; its log follows:"
        cat "$SWAY_LOG"
    fi

    if [ -s "$LOG" ]; then
        cat "$LOG"
    else
        echo "The verification produced no output. sway log:"
        cat "$SWAY_LOG"
        return 1
    fi
    return "$(cat "$RC" 2>/dev/null || echo 1)"
}

rc=0
run_session "side by side from the origin" "1280 0" || rc=$((rc + $?))
echo
run_session "negative origin" "-1280 0" || rc=$((rc + $?))

exit "$rc"
