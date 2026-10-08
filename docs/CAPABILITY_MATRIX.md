# Capability matrix

Status meanings: **stable** is compatibility-supported, **beta** is suitable
for evaluation with documented limitations, and **experimental** may change
without a compatibility window.

| Capability | Status | Windows | Linux X11 | Linux Wayland | macOS |
|---|---|---:|---:|---:|---:|
| Mouse, keyboard, screenshot | stable | CI | CI/Xvfb + xev | CI/sway + libeis | implementation |
| JSON executor and variables | stable | CI | CI | CI | platform-neutral |
| Image and anchor locators | beta | CI | CI | implementation | implementation |
| Accessibility locator | beta | CI | CI/AT-SPI | CI/AT-SPI | CI (tree read) |
| Window management | beta | CI | CI/openbox | unavailable | CI (listing) |
| Recorder | beta | CI | implementation | unavailable | CI |
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

Linux X11 said `CI/Xvfb` for a long time on the strength of a job that
imported the package under `xvfb-run` and generated two lines of code. Nothing
moved a pointer, and every X11 assertion in the suite is made against a mock
of `python-Xlib`, so the questions that matter went unanswered: does an
injected event reach a client at all, does it arrive as *real* input, and is a
captured pixel the pixel on screen. The `x11-verification` job answers them
against a real Xvfb server with a real window manager, and it takes its ground
truth from other codebases than the one under test — `xev`, a real X client
that prints every event delivered to its window; ImageMagick's `import`, an
independent grabber, against a root window painted two asymmetric colours so a
wrong rectangle cannot look right; and `xdotool` / `xdpyinfo`, the server
answering for itself. It runs twice, over one monitor and then two.

One assertion there is worth naming, because losing it would be silent:
XTest-injected events must arrive with `synthetic NO`. `XSendEvent` traffic
arrives with `synthetic YES` and is discarded by most toolkits, so a backend
that quietly stopped driving real input would still pass every check that only
counted events.

There is deliberately no negative-origin X11 pass. On X11 the root window is
the union of every monitor and always begins at `(0, 0)`: a monitor placed to
the left shifts the others right rather than moving the origin. The Wayland
job's second layout has no analogue here — a protocol difference, not an
untested case.

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

The recorder row said `unavailable` for macOS while the code for one sat in
the tree unused, and the reason was real rather than an oversight: the old
listener built an `NSApplication` at import time and stopped recording with
`AppHelper.runEventLoop()`, a loop that never returns to its caller. Wiring
that up would have put both on the path of `import je_auto_control`, so
`wrapper/_platform_osx.py` set `recorder = None` instead.

Neither was necessary. A `CGEventTap` needs a **run loop**, not an
application: the tap is created on a dedicated thread, its source is added to
that thread's run loop, and the loop is pumped in short `CFRunLoopRunInMode`
slices so a stop flag is honoured between them — the same shape the macOS
hotkey backend already used. The tap is listen-only, because a recorder that
consumed events would swallow the input it is recording. This row says `CI`
because the `macos-capabilities` job records a real session on a real window
server: it posts a move, a click and a keypress through the public API and
asserts they come back out of the tap with the release and the coordinates
they were posted at.

Two defects were in that code and only a Mac could show them. Coordinates came
from `NSEvent.mouseLocation()`, whose origin is the **bottom-left** of the
display, while every replay posts into the top-left space `osx_mouse` uses —
so a click recorded near the top of the screen replayed near the bottom. And
modifiers were not recorded at all: macOS sends no key-down for Shift,
Control, Option or Command, only a `flagsChanged` event carrying the new flag
set, so a recording could not say a modifier was held across what followed.

The table has four columns because those are the four desktops with their own
backend, not because they are the only supported systems. Two more axes now
have CI behind them:

**The BSDs.** `platform_wrapper` refused to start on anything that was not
win32/cygwin/msys, darwin or linux/linux2, and every X11 backend module
carried its own copy of the same Linux-only guard — so a FreeBSD, OpenBSD or
NetBSD desktop, which runs the same X server and the same `python-Xlib` as
Linux, could not import the package at all. `python-Xlib` was pinned to
`platform_system=='Linux'` too, so even relaxing the guards would have left
the backend without its one dependency. The guards now ask
`utils/platform_id.is_x11_unix()` — "is this an X11 unix", which is the
question they were always trying to ask — and the `freebsd` job boots a real
FreeBSD 14 VM to run that decision on a system that is genuinely one.

For a while it checked that decision and nothing else, for a measured reason:
importing anything under `je_auto_control` ran the package facade, which
imported OpenCV and cryptography at module scope, and neither publishes a
FreeBSD wheel — installing them from ports pulled a dependency tree that had
not finished after fifty minutes.

That was the wrong thing to work around. Moving a pointer needs neither
package, so the facade stopped importing them (and NumPy, Pillow and
`je_open_cv`) at module scope; they belong to the functions that use them.
What the VM installs now is `python-Xlib`, `defusedxml` and an X server, all
of which take seconds, and `test/verify/freebsd_verify.py` drives the whole
backend on it. The reads come off the X server rather than out of this
codebase: `query_pointer` for the cursor and the button mask, `query_keymap`
for whether an injected key really went down, and a mapped X window that has
asked for button events for the wheel — which is what caught `mouse_scroll`
matching a literal `["linux", "linux2"]` and therefore doing nothing at all,
silently, on every BSD.

**arm64.** `macos-14` was already arm64; `ubuntu-22.04-arm` joins the
smoke matrix and passes. `windows-11-arm` was tried and removed, on
measurement rather than assumption, and **two** dependencies are why:
**opencv-python publishes no `win_arm64` wheel** in any version, so pip falls
back to building from source and CMake cannot configure for ARM64; and
**cryptography stopped publishing one after 46.0.3**, while this project's
floor is `>=50.0.0` — a security floor (GHSA-537c-gmf6-5ccf, then
GHSA-g6cj-pr64-35w5) that cannot be lowered to reach a wheel. The same floor
costs Intel Macs their prebuilt wheel: cryptography 49.0.0 stopped publishing
`macosx_10_9_universal2` and ships `macosx_11_0_arm64` only, so `pip install`
on an x86_64 Mac compiles cryptography from source and needs a Rust toolchain
first. Neither is a CI problem to work around: the package
genuinely cannot be installed on Windows arm64 today. `Progress.md` records
both, alongside a `pip --dry-run --platform win_arm64` command that re-checks
them in seconds without an arm64 machine.

The accessibility row said `backend tests` for Linux X11 and meant nothing by
it: there was no Linux backend at all, and `_build_backend()` fell straight
through to the null one. There is one now, over **AT-SPI2** — which is a D-Bus
protocol rather than a library, and that is what makes it reachable without a
new dependency. The usual bindings (`pyatspi`, `gi.repository.Atspi`) are
distribution packages built against the system introspection data and cannot
be installed into a virtual environment, so depending on them would be
depending on something most users cannot get. The client written for the XDG
portal handshake already spoke enough D-Bus.

It is exercised by the `x11-verification` job against a real accessibility bus
and a real GTK application (`zenity`), because neither half can be mocked
usefully: the bus is D-Bus-activated rather than started by hand, an
application only appears on it if its toolkit bridge loaded, and the tree's
shape is the toolkit's business.

That job immediately found a gap in the shared D-Bus client: **it could not
demarshal signed integers.** The portal handshake never needed one, and
AT-SPI reports a component's extents as four *signed* values — because a
window on a monitor left of or above the primary one is at a negative
coordinate. Without it the backend could read a tree but not where anything
was. The client now handles the whole fixed-width numeric set except `h`
(UNIX_FD), which stays an error on purpose: it is an index into a descriptor
array this client does not receive, so returning it would hand a caller a
number that addresses nothing.

Because AT-SPI is a bus rather than a display protocol, this row is `CI/AT-SPI`
for **both** Linux entries: a Wayland session runs the same accessibility bus,
so this is the one capability where Wayland is not the restricted case.

Window management had no row here at all until it had more than one platform.
It was Windows-only for the project's whole life — the facade branched on
`sys.platform` and raised everywhere else — which left 23 `AC_*` commands and
their MCP tools dead on macOS and Linux. It now goes through a backend seam:
Win32, EWMH over python-Xlib on X11, and Quartz plus the accessibility API on
macOS.

The X11 half is exercised by the `x11-verification` job against a real
`openbox` session, driving the public facade and taking ground truth from
`xwininfo` and `xprop`. Two things only a real window manager could have
shown up came out of it, and both were wrong in the first implementation:

* **The rectangle is the frame, not the client.** Win32's `GetWindowRect`
  returns the frame — border and title bar included — and every caller here is
  written against that. Reporting the client area was off by the decorations
  on X11 alone, silently, and by a different amount per window manager.
* **A move must go through `_NET_MOVERESIZE_WINDOW`.** Under a reparenting
  window manager a client's own x/y are relative to its frame, so a direct
  `ConfigureWindow` asks for a position in the wrong coordinate space.
  Measured against openbox, asking for (300, 220) that way landed the window
  at (302, 260).

`post_key_to_window` and `post_click_to_window` work on X11 and are asserted
to arrive *flagged synthetic*, because that is what they are: `XSendEvent`
traffic, which GTK and Qt discard by design. They are the X11 counterpart of
Win32's `PostMessage`, which carries the same best-effort caveat. macOS has no
equivalent at all — an event goes to whatever has focus — so the backend
refuses rather than reporting a success that went somewhere else.

Wayland is `unavailable` and will stay that way: the protocol does not let a
client enumerate or move another application's windows. That is a design
decision upstream, not a gap here, and the backend selector says so instead of
looking broken.

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

What each of those outcomes *means* is now an explicit state rather than one
undifferentiated failure. `probe_capabilities()` (`AC_probe_capabilities`, the
`ac_probe_capabilities` MCP tool, and the Diagnostics tab) reports input,
capture, recording and the stop shortcut separately, each as `available`,
`not_requested`, `requesting`, `needs_permission`, `needs_setup`,
`session_closed`, `revoked` or `compositor_restarted`, with the backend
serving it and whether it reaches the whole desktop — which it does not when
the X11 backend is serving a Wayland session through XWayland. The probe asks
the desktop for nothing. Two outcomes no longer fall back to ydotool: a
consent the portal **denied**, and a session the compositor **revoked**; both
raise `WaylandAuthorisationError` until `reset_input_authorisation()`. Every
other failure falls back as before. The denial is recognised from liboeffis's
own error text, which only the `portal-verification` job can vouch for: it
prints how each of the six refusals is classified, with a `*** REVISIT ***`
banner if the dismissed dialog is not the one classified as declined. Until
that job has been read, treat "a denied consent stops the fallback" as
implemented against fakes and unverified against a real liboeffis.

The libei session can also be moved into a helper process
(`JE_AUTOCONTROL_WAYLAND_EI_WORKER=1`, **off by default**). The in-process
path and its deliberate one-context-one-descriptor leak on a half-open
handshake are unchanged and remain the default; the upstream `ei_unref` crash
is not fixed. `docker/libei_verify.py` now classifies that teardown — which
ways of ending a half-open context crash and which are clean — and counts
descriptors leaked in-process against through the helper, and
`docker/eis_verify.py` measures the helper's latency and what happens to a
held key when the helper is closed or killed. Those are printed as
measurements and never change either job's exit status.

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

## Capability states the code reports

The table at the top says what CI exercises. This section says what the
running program reports about itself, which is a different question and has a
machine-readable answer.

`probe_capabilities()` diagnoses four desktop capabilities separately —
`input`, `capture`, `recording` and `stop_shortcut` — and gives each one of
these states:

| State | Meaning | Usable now |
|---|---|---|
| `available` | Nothing stands in the way. | yes |
| `not_requested` | Usable; the desktop asks for consent on first use. | yes |
| `session_closed` | This process closed its session; the next use asks again. | yes |
| `requesting` | A consent request is on screen right now. | no |
| `needs_permission` | Someone has to say yes: a refused or unanswered consent, a device node this user may not read. | no |
| `needs_setup` | Something has to be installed or configured. | no |
| `revoked` | The compositor took a granted session away. | no |
| `compositor_restarted` | The grant came from a compositor that is no longer running. | no |
| `unsupported` | The platform cannot do this. | no |
| `unknown` | Not determinable without side effects. | no |

A state is a diagnosis, not a test result. On Linux every state comes from
what the probe could read without side effects — the environment, `PATH`, the
loader and the authorisation ledger — so `available` there means "nothing was
found in the way", not "an event was delivered". On the other two desktops the
probe reads nothing at all, and says so:

<!-- probe-capabilities:begin (generated: test_modernization_examples.py --fix) -->
| Platform | Capability | State | Backend | Evidence |
|---|---|---|---|---|
| `win32` | `input` | `available` | `win32` | reported, not probed: nothing to authorise |
| `win32` | `capture` | `available` | `win32` | reported, not probed: nothing to authorise |
| `win32` | `recording` | `available` | `win32` | reported, not probed: nothing to authorise |
| `win32` | `stop_shortcut` | `available` | `win32` | reported, not probed: nothing to authorise |
| `darwin` | `input` | `unknown` | `quartz` | not probed: permission for this platform is granted outside the process and is not probed here |
| `darwin` | `capture` | `unknown` | `quartz` | not probed: permission for this platform is granted outside the process and is not probed here |
| `darwin` | `recording` | `unknown` | `quartz` | not probed: permission for this platform is granted outside the process and is not probed here |
| `darwin` | `stop_shortcut` | `unknown` | `quartz` | not probed: permission for this platform is granted outside the process and is not probed here |
<!-- probe-capabilities:end (generated: test_modernization_examples.py --fix) -->

So a Windows or macOS row in a capability report is the backend's name and a
constant, never evidence that input works: on macOS the Accessibility and
Screen Recording permissions are granted in System Settings and are not
readable here. The `macos-capabilities` and Windows jobs in the table above
are what exercise those backends.

## Mobile devices

`mobile_capability_matrix()` is the source of the tables below: which
`AC_android_*` / `AC_ios_*` commands deliver each capability, and which
desktop features have no mobile counterpart. A session reports each capability
per device with `device_setup_report()`, in one of four states — `available`,
`needs_permission` (USB debugging not authorised), `needs_dependency` (for
example `uiautomator2` for multi-touch, or the ADB Keyboard IME for non-ASCII
text) and `unsupported` — together with the backend and the versions that
answered.

Every command below is exercised in CI against a fake `adb` host and a fake
WebDriverAgent client. That proves which commands are sent. **No job drives a
real Android device or a real iPhone**, so nothing here is hardware-verified,
and the row in the table at the top stays `mocked CI`.

<!-- mobile-matrix:begin (generated: test_modernization_examples.py --fix) -->
| Capability | Android commands | iOS commands |
|---|---|---|
| `input` | `AC_android_tap`, `AC_android_swipe`, `AC_android_key`, `AC_android_list_devices`, `AC_android_shell`, `AC_android_device_info`, `AC_android_long_press`, `AC_android_drag` | `AC_ios_tap`, `AC_ios_swipe`, `AC_ios_device_info`, `AC_ios_press_key`, `AC_ios_long_press`, `AC_ios_drag` |
| `unicode_text` | `AC_android_text`, `AC_android_type_text` | `AC_ios_type` |
| `multi_touch` | `AC_android_pinch` | `AC_ios_pinch` |
| `screenshot` | `AC_android_screenshot`, `AC_android_screen_info`, `AC_android_find_image`, `AC_android_find_text`, `AC_android_find_by_description`, `AC_android_self_heal` | `AC_ios_screenshot`, `AC_ios_screen_info`, `AC_ios_find_image`, `AC_ios_find_text`, `AC_ios_find_by_description`, `AC_ios_self_heal` |
| `ui_tree` | `AC_android_find_element`, `AC_android_click_element`, `AC_android_dump_hierarchy` | `AC_ios_find_element`, `AC_ios_click_element`, `AC_ios_dump_source` |
| `app_lifecycle` | `AC_android_launch_app`, `AC_android_stop_app`, `AC_android_app_state`, `AC_android_wait_for_app` | `AC_ios_launch_app`, `AC_ios_stop_app`, `AC_ios_app_state`, `AC_ios_wait_for_app` |
| `alerts` | `AC_android_alert_accept`, `AC_android_alert_dismiss` | `AC_ios_alert_accept`, `AC_ios_alert_dismiss` |
| `install` | `AC_android_install_app` | `AC_ios_install_app` |
| `files` | `AC_android_push_file`, `AC_android_pull_file` | `AC_ios_push_file`, `AC_ios_pull_file` |
| `clipboard` | `AC_android_get_clipboard`, `AC_android_set_clipboard` | `AC_ios_get_clipboard`, `AC_ios_set_clipboard` |
| `recording` | `AC_android_start_recording`, `AC_android_stop_recording` | `AC_ios_start_recording`, `AC_ios_stop_recording` |

| Desktop-only feature | Why | Use instead |
|---|---|---|
| Window management (AC_window_*, focus, move, resize, z-order) | a phone shows one app at a time; there are no windows to manage | launch_app / stop_app / app_state to choose what is in front |
| Mouse buttons, wheel and hover (AC_click_mouse, AC_mouse_scroll) | touch screens have no pointer, buttons or wheel | Tap, LongPress, Swipe (to scroll), Drag and Pinch |
| Keyboard shortcuts and modifier keys (AC_hotkey, AC_press_keyboard_key) | there is no physical keyboard or modifier state | type_text for text; AC_android_key / AC_ios_press_key for hardware keys |
| Desktop accessibility tree (UIA, AX, AT-SPI) | those APIs describe the host's desktop, not the device | AC_android_find_element (uiautomator2) / AC_ios_find_element (XCUITest) |
| COM / Office automation | COM is a Windows host API | none on the device; drive the mobile app's UI instead |
| USB host passthrough and usbip | these share the host's USB devices; a phone is a USB device, not a host | none; adb and WebDriverAgent are the device transports |
| Global hotkeys, triggers on host input, input recording | they observe the host's keyboard and mouse, which the device does not use | record executed mobile steps in the action journal |
| Desktop screen capture and screen recording (AC_screenshot, AC_screen_record) | they capture the host's monitors | DeviceSession.capture() and the recording extension |
<!-- mobile-matrix:end (generated: test_modernization_examples.py --fix) -->
