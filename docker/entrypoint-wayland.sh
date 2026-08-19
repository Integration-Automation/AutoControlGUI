#!/bin/sh
# Bring up a headless sway session and run the Wayland verification in it.
#
# The verification has to run *inside* the compositor's session, because
# WAYLAND_DISPLAY is what makes grim, wtype and wlr-randr able to talk to it
# at all — and what makes AutoControl's platform wrapper select the Wayland
# backend. sway execs the script, the script writes its log and exit status
# to files, and this wrapper reports both once sway is gone.
#
# It does that twice, over two output layouts:
#
#   * side by side from the origin — sway's own default for two headless
#     outputs, and what a single-monitor desktop looks like too;
#   * HEADLESS-1 moved to (-1280, 0) — what a desktop looks like whenever a
#     monitor sits left of (or above) the primary one. The whole-layout
#     capture then starts at a negative coordinate, so every mapping between
#     a pixel and a screen coordinate has to subtract that origin. sway's
#     headless backend accepts a negative `position`, and grim accepts a
#     negative `-g`, so this is a real compositor answering rather than a
#     mock agreeing with itself.
set -eu

RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/xdg}"
mkdir -p "$RUNTIME_DIR"
chmod 700 "$RUNTIME_DIR"

LOG=/tmp/verify.log
RC=/tmp/verify.rc
SWAY_LOG=/tmp/sway.log

# The two outputs are painted different solid colours. A uniform screen would
# let a wrong region grab look right, and identical colours would let a
# red/blue swap through — these do neither. The values are mirrored in
# wayland_verify.py as OUTPUT_COLOURS.
cat > /tmp/sway.cfg.in <<'SWAYCFG'
default_border none
output HEADLESS-1 position @POS1@ bg #123456 solid_color
output HEADLESS-2 position 0 0 bg #abcdef solid_color
exec sh -c 'python3 /opt/verify/wayland_verify.py >/tmp/verify.log 2>&1; echo $? >/tmp/verify.rc; swaymsg exit'
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

    # sway's own chatter goes to a file: it is only interesting when the
    # session fails to come up at all, and it would otherwise bury the
    # verification.
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

# The libei half needs no compositor — it drives the binding against the real
# libei.so — so it runs after sway is gone rather than inside a session.
echo
python3 /opt/verify/libei_verify.py || rc=$((rc + $?))

exit "$rc"
