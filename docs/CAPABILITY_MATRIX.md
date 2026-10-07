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
| Device-frame Unicode / gestures / OCR-template-VLM healing | beta | controlled SDK tests | controlled SDK tests | controlled SDK tests | controlled SDK tests |
| Frozen mobile contexts / owned matrix / passive probe | beta | controlled SDK tests | controlled SDK tests | controlled SDK tests | controlled SDK tests |
| LLM/VLM agents | experimental | fake-backend CI | fake-backend CI | fake-backend CI | fake-backend CI |
| USB passthrough | experimental | hardware-unverified | backend tests | backend tests | hardware-unverified |

“Implementation” means code exists but the repository does not currently run a
real OS runner for it. It must not be interpreted as a production guarantee.
Hardware-backed results and known limitations should be attached to releases.

Mobile context evidence uses fake SDK/transports and offscreen Qt: parallel default
isolation, owned ADB argv/timeouts, cancellation during construction/request,
rejected late completion, owner-only helper cleanup and matching probe surfaces.
Passive probes inspect dependencies without SDK loading, device scanning or input;
dependency discovery is not device connectivity/authorization. `connected` means
logical lifetime. Remote probes require MANAGE_HOSTS. Matrix duplicate detection
compares configured targets, not physical identities hidden behind endpoint aliases.
Real Android/emulator and remote-WDA reachability, authorization, SDK bootstrap
total deadlines and recovery remain H3 acceptance cases in Progress.md. Unicode,
gestures, frames and observed app lifecycle are delivered in E2–E3; the Mobile devices panel retains an explicit owner.

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

**Crypto installation snapshot (2026-10-03).** The required cryptography floor
is >=50.0.0; uv.lock resolves 50.0.2. The upstream PKCS#7 advisory is moderate
and fixed in 50.0.0; AutoControl does not invoke PKCS#7 decryption. See the
[upstream advisory](https://github.com/pyca/cryptography/security/advisories/GHSA-g6cj-pr64-35w5)
and [PyPI release files](https://pypi.org/project/cryptography/50.0.2/#files).

| Target / Python 3.12 binary probe | cryptography>=50.0.0 | Base profile / affected features |
| --- | --- | --- |
| Windows x64 (`win_amd64`) | 50.0.2 wheel resolves | Crypto regressions pass with an isolated 50.0.2 wheel. |
| Windows arm64 (`win_arm64`) | No matching wheel; newest offered 46.0.3 | Markers exclude crypto/OpenCV/je_open_cv, keeping imports and noncrypto capabilities available. Encryption, vault, Ed25519, TLS/ACME and encrypted recording require a compatible local crypto build. |
| Intel Mac (`macosx_10_9_x86_64`) | No matching wheel; newest offered 48.0.1 | Crypto stays required; installation needs a source build. Do not lower the security floor. |
| Apple Silicon | PyPI lists macosx_11_0_arm64 wheels | Metadata verified; native installation is covered by the later platform matrix. |

Reproduce each crypto probe separately (pip --platform does not change PEP 508
marker evaluation on the running host):

```sh
python -m pip install --dry-run --only-binary=:all: --no-deps --platform win_arm64 --python-version 3.12 --target ./probe-win-arm 'cryptography>=50.0.0'
python -m pip install --dry-run --only-binary=:all: --no-deps --platform macosx_10_9_x86_64 --python-version 3.12 --target ./probe-intel-mac 'cryptography>=50.0.0'
```

Source builds need Rust and native build dependencies; follow the
[official installation guide](https://cryptography.io/en/latest/installation/).
`CryptoDependencyError` identifies unavailable crypto features;
`CryptoUnavailableError` also remains a RuntimeError, and `CryptoImportError`
remains an ImportError. Each message includes `pip install "cryptography>=50.0.0"`.
Public imports stay Qt/crypto-free; unsupported crypto features fail individually.

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
refuses what no region covers, without switching the authorized transport.

The `ydotool-verification` job covers explicitly configured CLI input
(`JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=cli`). A seat makes an injected event arrive
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

Remote request limits propagate through device workers, parallel branches, DAG
nodes, observers, schedules, triggers and hotkeys. Independent requests and
deferred deliveries isolate variables. Filesystem roots constrain declared
arguments and configured signing/encryption key paths; process tools require
admin and remain outside an operating-system sandbox. Physical mixed-DPI,
Retina, keyboard-layout, USB and macOS accessibility checks remain in Progress.md.

Structured journals have controlled tests for secret masking before append,
nested/parallel provenance, interrupted status, read-only GUI preview and
shared AC/MCP/Script Builder adapters. These are fake-handler/offscreen
contract checks, not evidence of physical-device replay.

Fixed-frame self-healing comparisons and template revision controls are available
through typed headless APIs, facade, six AC/MCP commands, Script Builder and the
Self-Healing Actions menu. Synthetic dataset tests cover changed templates,
negative origins, scales, expected misses and unknown labels. Root checks,
immutable snapshots, validation and baseline hashes guard acceptance/reversion.
Offscreen GUI and fake backend tests verify provenance and delegation, not paid
model quality or physical-device operation success. See `benchmarks/self_healing`.

Journal candidate generation has controlled tests for selected-run provenance,
observed branches/parallel ordering/retry occurrences, secret reference retention,
masked/incomplete/failed omissions, input-as-data safety, installed plugin
validation, CLI export and separate GUI preview/import. API, facade, AC, MCP,
Script Builder and Recording Editor use the same core. These tests and
`benchmarks/journal_codegen` do not certify physical replay or unobserved paths.

Whole-B review regressions cover positional resolved credentials and sensitive getter outputs before append/logging, unhandled loop/parallel/catch failures versus successful recovery, omitted variable-dependent candidates and required block arguments without dispatch. These remain controlled headless checks.

Persistent config server is Beta with controlled SQLite/TestClient/loopback tests for restart, concurrent writers, idempotent retries, account isolation and migration guards. Physical multi-device convergence, config GUI and offline causal client are not claimed by this server-only increment.

Causal config sync and durable outbox are Beta. Controlled HTTP/SQLite tests cover real interleaved CAS writes, clock skew, preserved conflicts, lost replies/restart, bounded retry/cancellation, shared peer acknowledgements and explicit retired-device full resync. No physical multi-machine or GUI delivery is claimed by this increment.

Definition/asset sync is Beta: controlled HTTP/SQLite, file integrity and offscreen Qt verification; physical multi-machine evidence remains pending. Config Sync covers explicit preview/exchange/apply/retry/status/assets; folder and TCP clipboard suppress incoming echoes. All remote config commands retain MANAGE_HOSTS authorization and scoped filesystem metadata; advisory tool annotations do not grant permission.

Owned remote sessions are Beta and process-local. Controlled TCP/WS/WebRTC transport doubles and offscreen Qt verify independent defaults, owner-only disconnect, generation checks after queue/modal handoffs, failed-cleanup retry and WebRTC background disposal. Physical multi-machine verification remains pending. All new lifecycle/transport tools require MANAGE_HOSTS; read-only annotations do not bypass authorization.

Whole-C controlled SQLite/network-boundary and actual offscreen Qt regressions cover delayed Apply with eventual tombstone GC, receipt reconciliation, stale/exhausted/offline recovery, privacy revalidation, final Quick Connect generation delivery, WebRTC video/reconnect guards, legacy clipboard A→B→A and retained draining folder senders. Physical multi-machine/native/paid API/downstream checks remain H3.

Passive Wayland permission reporting (D1)
---------------------------------------

`probe_capabilities()` independently describes input and capture using
`available`, `needs_permission`, `needs_dependency` and `unsupported`, with
reason/recovery/scope. A discovered library/helper or configured command is
not proof of a usable compositor grant. XWayland is never reported as desktop
wide; restore tokens are unsupported by the current liboeffis binding.
Cancellation, timeout, live grant revocation and paused/removed devices are
covered by fake-library/headless tests. Those tests do not establish GNOME/KDE
acceptance or native libei teardown safety; real Linux evidence remains D2/D3/H3.

Native EI teardown verification (D2 checkpoint)
--------------------------------------------

Subprocess probes in `docker/libei_verify.py` and `docker/eis_verify.py`
require markers around `ei_unref`, distinguish setup failures from native
crashes, and enforce a 60-second deadline. Docker CI keeps their output as
`ei-native-verification` and preserves sway output as
`wayland-native-verification`, including failures.
The EIS image also ships the half-open probe; it can run independently with
`docker run --rm --entrypoint python autocontrol-eis:latest /opt/verify/libei_verify.py`.
The isolated Linux measurement of libei `1.3.901-1` confirms SIGSEGV on
half-open cleanup; completed sessions release device references and the
sender safely. Local runs pass 9/9 libei and 20/20 EIS checks; the EIS peer
does not announce pause or preserve the emulation sequence number, so those
conditions remain unverified. Desktop grant/device lifecycle acceptance remains
open in `Progress.md`; this checkpoint is not completion of D2.

Process-owned EI sessions (D2 helper stage)
-----------------------------------------

The default libei transport uses a dedicated helper and a private bounded JSON
channel (64 KiB, 128 events). Timeout/cancellation/death closes that channel and
reaps the worker without replay; explicit retry creates a new grant. Direct
`LibeiBackend` callers still own their process lifetime. Normal EOF cleanup
releases held keys/buttons on the same grant; after a native crash the
compositor owns revoked-device cleanup.

`docker/ei_worker_verify.py`, also retained by Docker CI, passed 3/3 checks
locally on Linux/Python 3.12 with a real EIS peer: exact input delivery and
held-Shift release on normal close, three half-open failures with parent fd
count unchanged (7 to 7), and SIGABRT containment with faulthandler evidence
and EIS disconnect. Fifty permission round trips measured p50 0.18 ms and
p95 0.25 ms on that container; these are transport measurements rather than
desktop response times. Unit tests also cover Windows socket sharing, typed
dependency errors, stale replies and concurrent cancellation. This does not
verify physical GNOME/KDE key-state recovery after crashes; D3/H3 desktop
acceptance remains pending.

NumPy/Pillow image backend (D2)
------------------------------

The shared image seam prefers OpenCV and lazily selects NumPy/Pillow when it
is absent. Windows arm64 installs NumPy 2.4.6 on Python 3.11+; binary-only
dependency resolution succeeded for CPython 3.11, 3.12, 3.13 and 3.14.
OpenCV and cryptography >=50.0.0 still fail binary resolution on that platform;
the safe crypto floor and shared exclusion markers remain in both distributions.

| Capability | NumPy/Pillow implementation | Evidence |
| --- | --- | --- |
| Template search, including negative origins and multi-match previews | Gray TM_CCOEFF_NORMED, uint8/float32 arrays or 8-bit image files | Controlled OpenCV-blocked tests; seeded scores and tile edges compared with OpenCV on Windows x64 |
| BGR screenshots | RGB/RGBA conversion preserving uint8 ndarray output | Controlled capture fixture; RGB/gray conversion compared with OpenCV |
| Image files and preview | Pillow decode/encode with non-ASCII paths; writable preview copies | Controlled PNG round trip and immutable gray-frame tests |
| Fixed-frame self-healing | Same image seam; prediction backend identifies numpy-pillow | Existing self-healing regression contracts |
| General OpenCV processing and video | Requires OpenCV/je_open_cv | Strict backend accessors report typed dependency errors |
| Native Windows arm64 execution | Platform smoke includes image tests without desktop input | Pending hosted-runner evidence in H3; wheel resolution is not CPU execution |

Frames are bounded at 16,777,216 pixels and each tiled FFT at 4,194,304 cells.
Unsupported fallback methods, dtype, decode format or scratch budget raise
framework image errors. Correlation scores preserve the normalized-coefficient
contract within the tested tolerance; they are not promised to be bit-identical.
Stable and development package install/build declarations are checked for parity.

Physical recording and portal stop foundation (D3)
------------------------------------------------

Beta `PhysicalRecorder.start([InputDevice(path)])` explicitly opts into
reading at most 16 existing physical Linux event nodes, with a 20,000-event
capacity. It never grabs devices or changes ACLs. Kernel virtual/uinput sources
are excluded before open. Stop returns raw events, including unchanged relative
or absolute device units; these are not desktop positions or replay commands.
Existing executor action journals require no global input hook. Read failure,
removal, SYN_DROPPED and incomplete events fail the recording; removing an ACL
after opening a descriptor does not itself revoke that descriptor on Linux.

`StopShortcutSession.start(on_stop, preferred_trigger='F7')` explicitly requests
a GlobalShortcuts binding asynchronously. The portal may change the actual
trigger, exposed as `trigger_description`. Refusal/timeout is retained until
explicit close/start; hold activation is debounced and grant revocation signals
stopping. Each method/response wait has a 30-second budget; close cancels the
owned request/session and can abort its connection. A blocked callback leaves
cleanup available for retry. The callback must signal cancellation promptly.

Controlled tests cover source exclusion, partial startup cleanup, capacity,
partial records, rejection, pending-request close, foreign sessions, early
activation ordering and revocation. The Beta/facade, five AC/MCP/Script Builder adapters and owned Diagnostics panel
share recording/stop services. All five remote operations require MANAGE_HOSTS;
raw stop output is masked in journals. Native GNOME/KDE authorization/keyboard
recovery remains in Progress.md. See `docs/WAYLAND_ACCEPTANCE.md` for the manual
authorization and physical-device procedure.
Specifications: [Linux input events](https://www.kernel.org/doc/html/latest/input/event-codes.html)
and [GlobalShortcuts](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.GlobalShortcuts.html).

Native default authorization uses a separate connection-attempt lock, with
active/pending owners detached under a short cache lock. Stop/reset cancel
pending IPC and stale completion cannot publish its grant; permission polling
also leaves the cache lock free. Tests include controlled workers without
performing desktop input.

GlobalShortcuts availability is revoked when its portal owner disappears or is
replaced. Pending consent fails and an active grant signals its owned callback.
The installed-wheel/private-bus GDBus checks exercise wire transport and grant
ownership; GNOME/KDE human consent and physical key-state recovery remain unverified.

GUI live-language registries preserve child wrappers and weakly reference self
entries. Ownership tests cover a USB prompt and self-registered tab titles,
including background GC and subsequent language switching. Historical Qt
segfault closure still requires native regression evidence.

Shared D-Bus cancellation detaches the connection and wakes pending I/O. The
last in-flight operation closes its descriptor; read polling checks cancellation
every 100 ms while preserving the original request deadline. Late completion
is rejected, and reconnect is refused until the previous descriptor has drained.

macOS Quartz/AppKit and the recording tap load only for native operations,
so imports and pure CLI file errors do not initialize those frameworks.
Explicit `grab_logical(metrics=...)` selects virtual-frame geometry on every
host; default macOS capture retains per-display Retina normalization. EI helper
cancellation also retains its socket until the transaction exits, polls reads
without shortening the total deadline and rejects completion after cancellation.

Native recording verification: Docker seat/uinput checks resolve real ydotool
nodes under `/sys/devices/virtual/input`, exercise the installed-wheel recorder,
and fail on opening a selected virtual source, accepted recording or FD leakage.
This covers kernel source exclusion; it does not establish positive physical
capture or GNOME/KDE consent and key recovery. Manual Docker scope: `d3-native`;
seat/ydotool native logs are retained for 14 days even on failure.

Mobile device frames retain immutable PNG, native orientation/viewport and display
rotation. Pixel-to-point conversion is explicit; captured geometry changes or
aspect mismatch fail instead of guessing. SDK Unicode does not fall back to ADB
input text. WDA pinch requires the W3C `/actions` endpoint and errors are typed;
Android two-pointer input uses the SDK RPC contract. OCR/template/VLM consume
supplied frame bytes. Bound self-heal captures once and taps the mobile owner.
Desktop screen regions/mouse buttons are unsupported in that binding. JSON mobile
services share facade/AC/MCP/Builder and Device Matrix Actions; remote calls need
MANAGE_HOSTS. Native emulator/WDA/rotation and SDK IME/clipboard restoration are
H3 acceptance, not established by controlled fixtures.

### E3 observed apps and extension capability evidence

Controlled transport tests cover Android launch/pidof/force-stop and owned WDA
creation/app-state/termination/alert routes. WDA states 0/1/2–4 map to
not_installed/not_running/running; Android pidof observes process presence only.
Connection failures never mean not_running. WDA cleanup targets a confirmed owned
ID, preserves borrowed sessions, retries failed DELETE and rejects late app input.
A first WDA construction shares the caller's poll budget; launch shares its
request/state deadline. Real native server/device behavior remains H3.

| Operation | Android | iOS | Evidence / recovery |
| --- | --- | --- | --- |
| launch/state/wait/stop | owned ADB | owned WDA app session | controlled transport; authorize selected device |
| alert accept/dismiss | unsupported | WDA endpoint | Android: specific UI-tree selector |
| install | APK via ADB | configured extension | native dependency/optional adapter, no fake success |
| files | ADB push/pull | configured extension | root-checked local paths; conservative native remote paths |
| clipboard | SDK Unicode | configured extension | dependency only until explicit operation; journals mask data |
| recording | configured extension | configured extension | needs_dependency without owner factory; bounded clip contract |

MobileExtensionSpec metadata is immutable/passive; creating a session or querying
capabilities performs no SDK import, connection or input. A configured adapter's
missing operations are unsupported; factories receive context/guard and must own
request budgets/cancellation/cleanup. Factory/context validation and controlled
recording dispatch do not establish physical recording acceptance. All three
JSON services share facade/API/AC/MCP/Builder/Device Matrix Actions and remote
MANAGE_HOSTS checks. Emulator signing/authorization and real-WDA recovery remain H3.

WDA creation can replace an existing server session. Controlled negative tests now prove that status reporting a borrowed ID or lacking ownership metadata produces no POST/DELETE, and a nested pending owner for the same URL cannot supersede the first. A bounded status check plus local endpoint lease protects detected/exact local owners; it cannot atomically exclude external clients or aliases. Dedicated idle endpoints and unknown-reply inspection remain operational requirements. Primary sources: [WDA creation](https://github.com/appium/WebDriverAgent/blob/master/WebDriverAgentLib/Commands/FBSessionCommands.m), [ownership response](https://github.com/appium/WebDriverAgent/blob/master/WebDriverAgentLib/Routing/FBResponsePayload.m).

### E4 delivery surfaces and setup evidence

`mobile_surface_matrix()` returns all 13 operation/API/AC/MCP/GUI catalog rows and
all actual executor commands with scope, reason and alternative. Alias enums come
from that catalog. A persistent Mobile devices owner permits app/frame workflows;
its six Actions include passive inspection, explicit authorization diagnosis,
operation/batch execution and immediate revocation/background close.
Controlled tests cover remote WDA GET status without session creation, Android
unauthorized zero input, platform mismatch, complete batch rejection, cleanup retry,
late callback rejection and plain-log privacy. They are not native device evidence.
Android Docker/KVM and remote WDA smoke configurations are delivered in
[MOBILE_SETUP.md](MOBILE_SETUP.md); native smoke emits actual/skipped results.
Physical Unicode focus, rotation/recovery and Apple signing/WDA remain H3 evidence.

Native Android evidence: [Mobile smoke 37625736780](https://github.com/Integration-Automation/AutoControlGUI/actions/runs/37625736780)
on source 21e02733 passes Android14/API34 Docker/KVM explicit get-state, observed
com.android.settings launch/stop and a real 1440×3040 device PNG. ADB1.0.41 /
platform-tools34.0.4-debian, uiautomator2 3.7.0 and adbutils 2.12.0 are retained
with the artifact. It does not establish physical-device, Unicode, rotation or iOS behavior.

### F1 lazy GUI evidence

All 50 catalog keys remain reachable; startup builds record/script_builder/
remote_desktop only. Fresh-process tests verify unopened Mobile and Screenshot
modules are absent, passive catalog/registry imports load no Qt, hide/reveal retains
widget identity/data and close/reopen retains key while replacing the widget.
Real Presence subscriptions return to baseline after deferred deletion. Existing
Actions and teardown audits explicitly open every feature to retain full coverage.
These offscreen tests are GUI lifetime evidence, not physical platform input proof.

### F2 workspace evidence

Six controlled Qt subprocess cases cover full 50-key reachability without unopened
Mobile/Screenshot construction, Ctrl+K/Enter, active Actions, stable language/input
identity, light/dark font refresh, 640×480 geometry, scroll access to 1200-pixel
content and explicit seven-state/recovery rendering. Actual Windows Qt offscreen
frames plus versions/fonts are retained in benchmarks/results/gui-workspace-f2.
No native input or permission operation is performed. Shared task cancellation is
F3; native desktop/mixed-DPI/physical recovery remains Progress.md/H3.

### GUI task and resource ownership (F3)

Controlled Windows/offscreen Qt cases verify responsive waits, owner/run/session
revocation, nested cancellation, raw input ownership, independent recording and
retained cleanup failures. Native TCP frame/approval tests verify asynchronous
connection completion. Device/recognition/network work and explicit service stops
run off Qt; local editing, bounded metadata and Qt dialogs/rendering stay on Qt.
The [50-key I/O audit](GUI_TASK_LIFECYCLE.md) separates shared tasks, legacy workers,
custom stop Events, global service control and passive/local views.

Raw GUI holds require known initial state and preserve previously pressed inputs;
unknown state reports unsupported before acquisition. Native key-state races with
other clients, physical restoration, real GNOME/KDE permission prompts and mixed
DPI remain H3. Raw headless APIs keep their existing behavior. Owned GUI recording
uses independent Windows/macOS instances or an X11 subscription; unsupported stacks
fail before allocation. Controlled X11/recorder fixtures do not constitute native
physical capture evidence. Cancellation drops late delivery and stops between
bounded operations; completed file/vault/global-service changes are not undone.

### F4 GUI reference evidence

Windows 11 build26300 / Python3.14.4 / PySide6.11.1 offscreen, one warmup plus
three fresh samples: startup median6698.29→5894.36 ms; tracemalloc peak
100860561→90167341 bytes (not RSS); Mobile first-open19.37→22.81 ms;
AC_sleep event-loop p95 median263.16→16.33 ms. Calibrated limits and six actual
Qt frames are retained under `benchmarks/results/gui-workspace-f4`. All50 keys,
default workflow, menu/navigation/cancel/close and synthetic DPI transforms pass
controlled regression. Native desktop layout/fonts/permission/input, physical
monitors and recording content remain Progress.md/H3; offscreen is not that evidence.

### MCP registry discovery

The same platform-neutral headless search/single-schema API is available through
facade, AC, MCP, Builder and the lazy GUI Tools inspector. Full schemas appear
only in explicit single-tool responses; summaries have bounded descriptions and
reviewed base capabilities, not verified native availability. Server queries use
live registry versions/plugins; local inspection uses the default registry.
RBAC/readonly checks run per query, and schema access cannot widen call roots/env
or privileges. Controlled tests cover snapshot copies, limits, viewer isolation,
readonly and removed tools; native device or consent operations are not needed.

### MCP session availability and paging

Controlled stdio/HTTP tests verify per-owner enable, idempotent owner-only list
changes, live standing-stream plugin notifications, original full-mode wire shape,
static fixed profiles, coherent old snapshot versions, foreign/expired/revoked
cursor failures, bounded caches/selections and session-drop reclamation. Stateless
requests use fixed deployment availability without session mutation or cursors.
Local preview via facade/AC/Builder/GUI and server-registry preview via MCP invoke
no tools or native probes. Availability changes do not widen RBAC/root/env/call
permissions; policy/cost regression is retained below; native integration remains H3.


### Policy and measured cost

Stdio flags `--tool-mode`, `--tool-profile` and `--tool-page-size` override corresponding
mode/profile/page-size settings; existing flags and full catalog inspection remain.
Readonly rejects mutating custom-registry calls as well as hiding/disallowing enable.
Availability never replaces the existing schema/RBAC/root/env/rate/confirmation checks.
Concurrent work captures accepted peer identity, roots and capabilities, including after
session removal; the original closed view lease cannot create a replacement session.
Controlled regressions verify root denial, authenticated audits and removed-tool rejection.
`benchmarks/mcp_discovery.py --output report.json` compares identical registry/policy
with one warmup/five samples and records source hash/platform/version. Reference:
full747/363544bytes, core6/2506bytes; local initialize+list37.91/9.56ms and
search9.78/9.65ms. This measures local JSON-RPC, excluding networking/native input.
Artifact: `benchmarks/results/mcp-discovery-g3/report.json`.

### Type evidence

Stable typing targets win32/linux/darwin without exemptions; strict new/rewritten scope includes all modernization modules. A separate `typing-extras` CI matrix installs GUI/WebRTC/Android/WDA SDKs and checks all modernization GUI modules against real PySide6 stubs on Python3.10/3.14. SDK protocols constrain adapter results; type success does not prove native authorization/device reachability. Local installed Qt checking and controlled mobile/GUI regressions are recorded in updates/H1.

### Metadata cross-check (H2)

Passive desktop keys: `input`, `capture`, `restore_token`. Metadata is not authorization evidence.

| Mobile operation | Facade | Command | MCP |
| --- | --- | --- | --- |
| `device_setup` | `mobile_setup` | `AC_mobile_setup` | `ac_mobile_setup` |
| `capture` | `mobile_capture` | `AC_mobile_capture` | `ac_mobile_capture` |
| `perform` | `mobile_gesture` | `AC_mobile_gesture` | `ac_mobile_gesture` |
| `type_text` | `mobile_type_text` | `AC_mobile_type_text` | `ac_mobile_type_text` |
| `launch_app` | `mobile_app` | `AC_mobile_app` | `ac_mobile_app` |
| `wait_for_app` | `mobile_app` | `AC_mobile_app` | `ac_mobile_app` |
| `app_state` | `mobile_app` | `AC_mobile_app` | `ac_mobile_app` |
| `stop_app` | `mobile_app` | `AC_mobile_app` | `ac_mobile_app` |
| `alert` | `mobile_alert` | `AC_mobile_alert` | `ac_mobile_alert` |
| `install` | `mobile_extension_action` | `AC_mobile_extension` | `ac_mobile_extension` |
| `files` | `mobile_extension_action` | `AC_mobile_extension` | `ac_mobile_extension` |
| `clipboard` | `mobile_extension_action` | `AC_mobile_extension` | `ac_mobile_extension` |
| `recording` | `mobile_extension_action` | `AC_mobile_extension` | `ac_mobile_extension` |

These declarations describe the selected device surface; check its capability result before native use. Offline examples and controlled fixtures do not certify physical devices.

H3 acceptance tooling records controlled journal replay and durable sync restart with platform/backend/version, actual outcomes and existing artifact paths; offscreen GUI rendering is tested separately. macOS native JSON retains failed probes. Fifteen coverage CI jobs keep the existing floor. See [acceptance evidence](MODERNIZATION_ACCEPTANCE.md).
