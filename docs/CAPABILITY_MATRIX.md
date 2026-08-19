# Capability matrix

Status meanings: **stable** is compatibility-supported, **beta** is suitable
for evaluation with documented limitations, and **experimental** may change
without a compatibility window.

| Capability | Status | Windows | Linux X11 | Linux Wayland | macOS |
|---|---|---:|---:|---:|---:|
| Mouse, keyboard, screenshot | stable | CI | CI/Xvfb | CI/sway + libeis | implementation |
| JSON executor and variables | stable | CI | CI | CI | platform-neutral |
| Image and anchor locators | beta | CI | CI | implementation | implementation |
| Accessibility locator | beta | CI | backend tests | unavailable | backend tests |
| Recorder | beta | CI | implementation | unavailable | unavailable |
| Reports, trace, failure bundle | stable | CI | CI | CI | platform-neutral |
| REST, MCP, scheduler | beta | CI | CI | CI | platform-neutral |
| Remote desktop / WebRTC | beta | tests | tests | tests | tests |
| Android and iOS bridges | experimental | mocked CI | mocked CI | mocked CI | mocked CI |
| LLM/VLM agents | experimental | fake-backend CI | fake-backend CI | fake-backend CI | fake-backend CI |
| USB passthrough | experimental | hardware-unverified | backend tests | backend tests | hardware-unverified |

“Implementation” means code exists but the repository does not currently run a
real OS runner for it. It must not be interpreted as a production guarantee.
Hardware-backed results and known limitations should be attached to releases.

Linux Wayland is split: **capture is exercised by CI against a real
compositor; input is exercised by CI against a real EI peer and a real portal.**

Screen capture runs through the compositor's own tool (`grim` on wlroots,
`gnome-screenshot` on GNOME, `spectacle` on KDE), falling back to
`xdg-desktop-portal` over the session bus, instead of the X11-only Pillow/mss
path —
and `JE_AUTOCONTROL_WAYLAND_CAPTURE_COMMAND` covers a setup none of those fit.
The `wayland-verification` job in `docker/` runs the whole capture path inside
a headless sway session and checks it against pixels the compositor painted,
which is why this row says CI rather than “implementation”. It runs twice, over
two output layouts: side by side from the origin, and with the left-hand
output at x=-1280 — the layout of any desktop with a monitor left of the
primary one, where the compositor's plane starts at a negative coordinate and
a size, a crop or a located hit that assumes `(0, 0)` is wrong by the width of
that monitor.

One cross-platform difference falls out of the same job, and it is not one this
project can fix: **a Wayland capture may contain the mouse cursor.** No capture
here passes `grim -c`, so none of them asks for the pointer — but wlroots draws
a *software* cursor whenever the backend has no cursor plane, and a software
cursor is composited into the output buffer, which is the buffer
`wlr-screencopy` hands back. Headless is permanently in that state, and so is a
real desktop whose driver offers no cursor plane or whose user set
`WLR_NO_HARDWARE_CURSORS=1`, a common workaround. Windows' BitBlt and the X11
Pillow/mss path never include the pointer, so this is a Wayland-only
inconsistency rather than something callers already expect: with the pointer
resting on its target, a locator, a template match or an OCR read sees a
pointer-shaped hole in the middle of it. Both ways out need to know where the
pointer is — move it away and back, or mask around it — and Wayland does not let
a client read the cursor position, so the only source would be an in-process
record that goes stale the moment the user touches their own mouse; masking the
wrong place is worse than a visible cursor. So this is documented rather than
worked around: park the pointer away from the region of interest before
capturing. The `seat-verification` job asserts the behaviour as measured, so if
wlroots ever honours `overlay_cursor` for software cursors, CI goes red and says
so.

Input is verified in four parts, all of which are CI jobs.

The `eis-verification` job in `docker/` runs AutoControl's real `libei` sender
against a real EIS server — libeis, over a Unix socket, with no compositor
involved — and reads back off the wire what arrived: the capability and
event-type enum values, the variadic seat bind, the key codes, the absolute
coordinates, the button codes, the scroll unit and sign, and a frame per
emission. It also settles the absolute pointer's coordinate space, which is
where the negative-origin layout above reaches the input half: a region's
offset is part of the coordinate rather than something to subtract, and a
motion landing outside every region is dropped by libei without a return code,
an event or an error — so the sender maps the point into region space and
refuses what no region covers, which is what lets the `ydotool` path take it.

The `ydotool-verification` job covers the CLI fallback, which the `libei` path
drops to at every failure point. A seat is what makes an injected event arrive
somewhere; it is not what makes one observable, so no compositor is needed:
`ydotoold` creates an ordinary uinput device, the kernel publishes it as
`/dev/input/eventN`, and the job reads the `input_event` structs back off it.
That covers the `click` bitmasks, the split press / release edges drag depends
on, what `mousemove --absolute` really puts on the wire, the wheel signs and
axes, numeric key codes, and — in the last check — the argv the mouse and
keyboard backends build for themselves.

The `seat-verification` job is where an injected event finally reaches a
compositor, and it settles what `mousemove --absolute` is absolute *to*. That
had been recorded as needing a VM running a desktop that consumes libinput
devices; it needs three environment variables instead. wlroots takes
`WLR_BACKENDS=headless,libinput`, so the outputs stay virtual while the input
half is the real libinput backend; libseat's builtin backend opens the device
without logind; and `SEATD_VTBOUND=0` stops it reaching for a VT no container
owns. `grim -c` then draws the cursor into a screenshot, so the compositor
answers in layout coordinates. Two findings come out of it, over the same two
layouts the capture job uses. The origin `--absolute` counts from is the
top-left of the *output layout*, not layout `(0, 0)` — the same distinction
the capture path already makes, and the reason `set_position` now subtracts
`layout_origin()` before calling ydotool. And the displacement is relative
motion, so the compositor's pointer acceleration scales it: libinput's default
adaptive profile moves the cursor twice as far as asked, which is what
ydotool's own `--help` means by "You need to disable mouse speed acceleration
for correct absolute movement". **The ydotool fallback is therefore only
pixel-accurate on a session whose pointer acceleration is off**; the libei
path is absolute at the protocol level and is unaffected.

The factor is compositor configuration and no client can read it back, so the
library cannot compensate for it — only the operator knows whether it is off.
`JE_AUTOCONTROL_WAYLAND_POINTER_ACCEL` is how they say so, and it applies to
the ydotool path alone: unset (or set to anything unrecognised, which says so
and falls back) warns once per process and sends the move anyway, `flat`
declares acceleration off and moves silently, and `strict` refuses the move
rather than let a click land somewhere else.

The `portal-verification` job covers how a client reaches libei on GNOME and
KDE, which is not a socket path but a file descriptor handed over D-Bus at the
end of the `org.freedesktop.portal.RemoteDesktop` session dance. That had been
recorded as needing a real desktop, on the grounds that no container ships a
RemoteDesktop portal — but the portal is a D-Bus interface, so the job owns the
well-known name itself and runs the real `liboeffis` through the real
handshake, ending in a live connection to the same `libeis` server the
`eis-verification` job uses. It settles the call order and the predicted
request paths, the device mask a user would be consenting to, that the
descriptor carries a real EI session, and that input emitted through it is
recorded at the far end. Every refusal is covered too — a dismissed dialog, a
dialog left open, a withheld descriptor, a closed session, a portal too old for
`ConnectToEIS`, no portal at all — each of which has to fail closed on
AutoControl's own clock.

What is still not covered is the consent dialog as a *dialog*: no user
dismisses anything in CI, so what a real dialog looks like and how long a real
one blocks stay mutter's business. The compositor also refuses global input
recording, key hooks, cursor-position reads and per-window injection outright;
those are Wayland design decisions, not gaps. See `Progress.md`.

One packaging note that affects users more than any of the above: ydotool 1.0
replaced its entire command line, and everything this backend builds arrived
in that release. Debian trixie ships no `ydotool` package; bookworm and every
current Ubuntu ship 0.1.8, which answers this argv with exit code 0 and no
events. AutoControl refuses that version up front rather than reporting
success for input it never sent.
