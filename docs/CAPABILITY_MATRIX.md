# Capability matrix

Selected dev pushes run `.github/workflows/ei-lifecycle.yml` in an isolated
libei/libeis container, retaining versions and both native logs for 14 days in
`ei-lifecycle-<run>-<attempt>` artifacts. Half-open and live cleanup children
have 10/60-second deadlines and faulthandler. Unrelated child failures fail CI;
successful cleanup requires begin/end markers. The half-open probe also requires
equal integer descriptor counts; live cleanup releases owned device refs first.
Run 39507190704 on libei/libeis 1.3.901-1 passes 9/9 and 20/20 checks, including
native out-of-region refusal without CLI fallback. Half-open `ei_unref` still
segfaults, so runtime protection remains and helper isolation is pending.
Device pause and sequence readback remain unverified. These controlled socket
peers do not establish compositor consent, physical or multi-monitor acceptance.

Status meanings: **stable** is compatibility-supported, **beta** is suitable
for evaluation with documented limitations, and **experimental** may change
without a compatibility window.

| Capability | Status | Windows | Linux X11 | Linux Wayland | macOS |
|---|---|---:|---:|---:|---:|
| Mouse, keyboard, screenshot | stable | CI | CI/Xvfb + xev | CI/sway + libeis | implementation |
| JSON executor and variables | stable | CI | CI | CI | platform-neutral |
| Structured action journals | experimental | controlled tests | controlled tests | platform-neutral | platform-neutral |
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

Journal storage, executor capture, provenance links, facade/CLI entry points
and Script Builder commands, observed runs and MCP journal tools have controlled tests. The journal work does not
claim native device acceptance. Run History journal browsing also has controlled offscreen tests.
Explicit manual history ownership has controlled API, command, CLI, GUI and MCP execution tests.
Self-healing cancellation and secret masking have controlled headless tests,
including registered command and MCP adapters; this adds no native or paid API acceptance.
Fixed-frame comparison has real local PNG/template tests, controlled VLM tests,
and API/CLI/command/MCP/offscreen GUI checks. Its synthetic quality populations
and wall-time percentiles do not establish native accuracy or speed improvements.
Runtime shared capture/region/provenance has controlled image/VLM, journal,
command/MCP and offscreen GUI tests. Explicit post-click callback/VLM verification
has controlled true/false/unknown, fresh-frame, preflight, exception and phase
cancellation tests across API/AC/CLI/MCP/GUI. Standalone VLM origin/Retina behavior
uses synthetic display/grabber tests. These checks establish no native accuracy
or paid-model acceptance; dispatch without a verifier remains unverified.
Original-step source inspection has controlled captured/legacy/unbound metadata,
run/step filtering, whole-file validation, revoked roots, cancellation, AC/CLI/MCP
and offscreen background-reader tests. It does not capture or replay device input.

Template-candidate lifecycle has local synthetic PNG, JPEG/BMP byte-preserving
rollback, labelled/unknown populations, file-conflict/concurrency, commit-boundary
cancellation, root-revocation and AC/CLI/MCP/offscreen GUI tests. The GUI retains
reviewed revisions and deferred authority. Eligibility means localization on the
supplied fixed images; this adds no native accuracy, performance or paid API claim.

Journal-to-code candidates have controlled run selection/lifecycle/parent/retry
provenance, strict/bounded schema, secret-reference and encoded-source redaction,
all-target static/dry-run, artifact integrity, path revocation, cancellation and
AC/CLI/MCP/offscreen review/import tests. A real virtual retry capture proves
source retention without duplicate replay. GUI import never dispatches input;
this adds no native-device or paid-API acceptance.

Persistent configuration has isolated SQLite reopen, multi-connection CAS,
account/payload identity, historical retry, capacity, lazy-path, authenticated
HTTP, legacy-opt-in and private AC/MCP/Builder checks. A local loopback server
exercises the real client protocol. These controlled tests do not establish
remote-machine convergence, causal merging, outbox or asset synchronization.

Local causal/outbox primitives have controlled conflict/resolution, clock-skew,
JSON type identity, peer acknowledgement/retirement, durable retry/prepare,
namespace/epoch, cancellation, bounded views/backoff and concurrent/stale-lease
tests, plus AC/MCP/Builder surfaces. The supplied-ledger collection check does
not perform server collection. The dedicated causal store and private version-three
HTTP route now validate authoritative membership/epoch transitions, explicit peer
acknowledgements and payload collection with permanent deletion fences. Tests cover
stale CAS, historical retries, forbidden legacy overwrites, retained alternatives,
fabricated acknowledgements, obsolete epochs and explicit restoration after GC.
Explicit CausalSyncClient/outbox HTTP delivery now has controlled tests for uncertain accepted sends, exact restart retry before fetch, bounded definite-rejection rebasing, operation-ID conflicts, retired peers, credentials, stale leases and atomic snapshot rollback/fork refusal. Durable explicit peer controls and atomic local full-resync now cover registration, ack/collection, retirement, uncertain restart retries, compact historical receipts, leases, pending-retirement consent and generation adoption. AC/MCP/Builder share the private control/status surface; the loopback example needs no optional web framework. Coordinated source workspaces are covered below; referenced assets are covered below; Sync UI controlled coverage is described below.

The dev/main headless suites retain merged process output, runtime/package
versions and child status for seven days, including failures. Linux collects
all-thread native backtraces through batch GDB; other platforms retain Python
faulthandler output. This is diagnostic infrastructure, not native lifecycle
acceptance or a root-cause correction; outstanding crashes remain in Progress.md.

Controlled region-authority checks cover automatic and native input selection,
exclusive region edges, gaps, raw-first/origin mapping, no-region devices,
same-sender retry, explicit CLI and original direct/wrapped control signals.
A refused native coordinate is failed and emits neither CLI input nor native
motion/frame/click. Fake-backend checks cover those boundaries; real-EIS run 39507190704 also
confirms out-of-region failure, zero native motion and no CLI fallback on
libei/libeis 1.3.901-1. Physical and multi-monitor acceptance remain deferred.

Passive capabilities are available through both SDK namespaces, one AC
command, one read-only MCP tool, Builder and explicit Diagnostics Actions.
Controlled checks cover independent input/capture prerequisites, denied/
paused/revoked/failed native state, nonblocking cached observations,
optional-absence-only CLI selection, invalid explicit capture commands,
XWayland scope limits, detached contexts and default metadata privacy.
Partial grants, paused optional button events and removed required pointer
devices have separate regressions; cached availability requires all requested
event families, rather than only the minimum handshake requirements.
Viewer executor plus real JSON-RPC dispatch and all four catalogues are
exercised. These are fake/offscreen metadata checks, not native device,
permission, compositor restart or full-monitor acceptance. Available
means last local observation; every actual operation still checks authority.

Active diagnostics now have controlled SDK/AC/MCP/GUI cancellation and
progress coverage. A real JSON-RPC server with two connection-scoped calls
using the same request ID cancels only the requested connection and uses
the existing -32800 response without ordinary error screenshots. The
window Actions provider exposes run/stop/passive inspection; GUI cases
cover duplicate runs, stop/retry, late closed results, destruction,
four-language state updates, plain-text errors and failed submissions.

Real socketpair waits and an owned temporary Python helper exercise
cancellation and reaping. Controlled protocol/native fakes verify partial
frames/writes, unchanged total deadlines, bounded Request.Close outside
the canceled scope, owned PNG removal, liboeffis unref and cleanup-error
priority. Native compositor consent UI, restore/restart, capture-owner
metadata and uncooperative extension cancellation are not established
by these tests and remain in Progress.md. Physical/API acceptance stays deferred.

Offscreen shared-task checks exercise GUI responsiveness, GUI-thread delivery,
cooperative session cleanup, owner/controller/handle destruction, collection
without callback retention, independent owner tokens, task-ID/terminal fences,
successful committed returns after a late stop, refreshed deletion/demotion/
corrupt-user refusal, context/viewer propagation, secret masking and error
formatter controls. Failed starts leave neither controller nor worker registry
entries. Retired jobs disconnect owner destruction hooks; a ten-task check
returns signal receivers to their primed baseline. These tests use events
and controlled functions, not network or
devices. Shared infrastructure is not evidence that every panel or native
backend already supports cooperative stop; those migrations remain in Progress.md.

Controlled diagnostic-interruption checks exercise six direct and explicitly
wrapped controls through the core, root SDK, versioned SDK and CLI. No later
check or ordinary error log occurs; the original control object propagates.
Ordinary RuntimeError/ValueError/OSError, including cyclic cause chains,
retain their failed-row and continuation behavior. An offscreen GUI test
uses the real runner with controlled checks, verifies cancellation leaves
the idle state, then performs a deliberate successful retry. No desktop
capture, native grant or cooperative worker-stop acceptance is implied.

Controlled offscreen Diagnostics checks cover idle construction, all four
catalogues, retranslation without execution, explicit Actions rendering and
original cancellation followed by deliberate retry. Providers are intercepted;
these checks acquire no portal grant or desktop input. Native consent, restore
and compositor-restart behavior remain pending in Progress.md.

Controlled screenshot-portal lifecycle tests cover bounded Request.Close on the
original bus, alternate/predicted handles, uncertain replies, direct/wrapped
controls, completed responses and partial connection cleanup. A real socketpair
with a full send buffer proves the call timeout also bounds a stalled write;
native descriptors close after interrupted connect/authentication/Hello. These
tests do not replace native compositor/consent-dialog acceptance in Progress.md.

Linux Wayland is split: **capture is exercised by CI against a real
compositor; input is exercised by CI against a real EI peer and a real portal.**

Controlled native-library tests cover portal refusal/timeout, incomplete
handshake, device pause/removal/disconnect, explicit reset/regrant and interrupted
chord cleanup. These states never implicitly replay key/button/pointer input
through CLI. Auto fallback remains for optional absence; forced libei refuses
absence as well. Cached refusal does not reopen consent. Explicit CLI selection
and the wtype text path remain available. These tests are not acceptance of a
real consent dialog, compositor restart or native teardown; those gaps and the
public input/capture capability probe remain in Progress.md.

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
refuses what no region covers. That refusal now carries failed state and stops
implicit CLI fallback, verified by the controlled socket peer in run 39507190704
with libei/libeis 1.3.901-1. This does not establish physical desktop acceptance.

The `ydotool-verification` job covers the separate CLI provider. Automatic
selection permits it only for optional native absence; native authority,
device and region refusals stop the request. A seat makes an injected event arrive
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

Explicit local asset-generation API/AC/MCP/Builder paths have controlled size/hash,
late-file failure, cancellation, live-root revocation, concurrent publication and cache
tampering coverage. Whole bundles publish only after every file is verified. The example
uses temporary local files and zero network/device calls. Configuration adapters and
referenced assets are covered below; controlled synchronization UI is covered below. Windows symlink creation may skip
locally when the account lacks that filesystem capability.

Seven local configuration adapters have controlled tests against actual JSON script files,
ElementRepository, HotkeyDaemon, TriggerEngine, AddressBook and JSON settings. Tests cover
restart-stable captures, concurrent alternatives, exact reviewed resolution, tombstones,
unchanged-source baselines, immutable receipts, cancellation/SQLite rollback, foreign and
corrupt storage, named references, recognized credential/path refusal and disabled native
profile generation. AC/MCP/Builder share private DRIVE and live root/cancellation guards.
Missing references and native binding type mismatches persist for review but block complete
publication. This establishes local capture/inert materialization, with no script execution,
vault lookup or listener startup; coordinated loopback convergence is covered below.
Native working-copy loading, folder and explicit clipboard lifecycle coverage, and live
GUI preference application are described below.

Controlled native-definition numeric tests refuse positive and negative 401-digit
JSON integers with ConfigSyncError before creating adapter storage.

A controlled POSIX temporary path reproduces the CI entropy false positive in local
bindings. The regression now accepts that private path while rejecting token-like
non-path strings and recognizable credentials embedded in an absolute path.

Saved native GUI preferences have controlled headless capture and offscreen real-QSettings
round-trip tests. The workspace adapter excludes other/private/geometry sections, keeps
concurrent values, gates exact reviewed resolution and emits versioned removals. Unknown
keys, wrong native types, extreme bounds, malformed/oversized INI fail before state I/O.
Tests compare native group/key case, exclude Python DEFAULT inheritance and confirm that
explicit new-GUI loading from a working copy preserves the immutable generation and the
current workspace. Seven domains publish together through AC/MCP/Builder. Explicit live-GUI application and Sync UI coordination are covered below; no native device acceptance is added.

Coordinated SyncWorkspace tests cover offline idempotent capture, two-source concurrent
conflicts/exact resolution, immutable generation publication, uncertain exact PUT retries,
retirement/full-resync baselines, new edits during an uncertain reset, permanent deletion
fences and historical reset idempotency after later work. Late SQL failures roll back
batch enqueue and reset baselines/intents atomically; owned outbox 1/2-to-3 and adapter
1-to-2 migrations preserve wire/source/receipt data. Invalid remote domains never reach
cache/prepared requests. Live roots, cancellation after accepted receipts, concurrent
coordinator leases, credential rotation/short masks and private INI error lines have
controlled regressions. AC/MCP/Builder round-trip and DRIVE/prestart refusal are covered.
The real temporary two-source loopback example converges without executing scripts or
changing active preferences. This establishes local HTTP integration, not device or paid
API acceptance. Referenced assets are covered below; controlled Sync UI integration is covered below.

Referenced asset tests verify durable per-account chunks/full-hash publication, exact
retries, late SQL receipt rollback, foreign/future database refusal, byte/object/user
quotas and corrupt-content rejection. Authenticated HTTP covers pre-body refusal,
accepted uncertain chunk restart, live environment rotation and prestart cancellation.
Workspace tests cover frozen offline assets, asset-only version changes, missing downloads
blocking complete generation, exact uncertain definition PUT before asset probe, reset
baselines preventing retired asset replay, cancellation/hard-carrier preservation,
private-field/credential-path refusal and disabled image-trigger output. Red regressions
fix relative asset paths following later cwd changes and resolution before local download.
The actual temporary stdlib loopback example transfers a real multi-chunk PNG and script
without execution, GUI starts, native device calls or active preference changes. Optional
FastAPI route tests skip when its extra is absent; local controlled routes are exercised.

Offscreen Sync UI tests run local capture/status on a background worker and real stdlib
loopback registration/synchronization. Receipt leaves the active window unchanged; exact
workspace review followed by explicit application updates theme/font/navigation and normal
close persists only the native preference whitelist. Concurrent alternatives resolve against
all reviewed entry heads. Source selection and close invalidate old results; late cancellation
blocks preference delivery. Captured contexts, stored-role revocation at core checkpoints and
queued delivery, pre-cancellation, bounded/finite JSON and network-secret error masking have
controlled tests. Headless API/AC/MCP/Builder share the exact reviewed preference operation.
This covers synthetic/offscreen/loopback behavior; device and paid API acceptance stays deferred.

Deterministic loopback tests pause a rejected TCP handler immediately after its AUTH_FAIL
write and admit a replacement at max_clients=1 before releasing that handler. Bad tokens,
wrong handshake phases and denied approval all cover the terminal-reply/capacity ordering.
The Windows/Python 3.10 CI race is reproduced without timing sleeps, native input or capture.

Native-load controlled tests construct real HotkeyBinding and all eight supported native
trigger classes/composites, with every node disabled and no polling/listener startup.
Independent mutable locator repositories, address books, settings, scripts and GUI preference
snapshots retain an unchanged immutable source. Typed assets rebase while literal strings and
secret placeholders keep their meaning. Exact digest, corrupt/resealed native files, enabled
children, literal/head disagreement, unreferenced files, source changes after initial review,
root revocation, mid-copy cancellation, wrapped hard signals and late committed stops are covered.
AC/MCP/Builder share private routing and prestart guards. Offscreen tests load without a source
configuration, inspect native kinds and explicitly open scripts/apply preferences with zero
script dispatch. Revoked owners and current viewers cannot perform later GUI actions.
The temporary example loads seven domains plus a real PNG without network/device/API calls;
this is controlled native-data integration and keeps physical/paid acceptance deferred.

Offscreen rendering regressions import unknown command names and positional values containing
HTML-like text. Selected displayed text must equal the complete original literal; both cases
fail with automatic rich-text interpretation and pass with literal text labels.

Controlled folder-core tests exercise same/older-mtime content edits, unchanged-content
touches, stopped multi-file sends, sender-initiated stop, blocked-worker ownership, restart
retry of pending/offline bytes and transient scan failure. Explicit receive receipts cover
no-echo behavior and races with older send, baseline and pruning operations. Wrapped
cancellation/KeyboardInterrupt/SystemExit carriers retain their original identities at scan,
send and receipt boundaries. These are local filesystem/fake-sender checks; native WebRTC
explicit GUI reconnect/resume is covered below; explicit clipboard lifecycle tests are described below.

Local bridge/fake-channel regressions verify observable callback failure, folder retry,
bounded buffering, queued cancellation, pending-abort ownership, completed-end cancellation
ordering, source-size mutation and refusal to write through a replaced bridge epoch.
Actual GUI folder toggles and direct factories stop on engine/viewer/peer/auth/role changes;
a controlled subprocess guards cancellation after scanning against lifecycle-lock deadlock.
Large inbox pulls yield the bridge loop; two downloads serialize without frame interleaving.
Queue overflow and cancellation before the first task step release capacity; stale failure
replies are suppressed and wrapped interruption objects survive error-reply callbacks.
These checks use local threads/files/fake channels, without real devices or paid APIs.
They do not establish remote publication acknowledgement, sender-checksum validation in legacy mode,
clipboard no-echo/disconnect behavior; the explicit clipboard coverage is described below.

Native receive lifecycle evidence covers deterministic close/write overlap, repeated close,
late frames, host/viewer stop, file/control channel close, all three terminal connection states,
replacement peer/channel, unauthenticated viewer refusal, permission revoke/regrant and stale
callbacks. A callback-driven immediate reconnect remains authenticated and publishes its new
transfer. Wrapped cancellation and hard signals retain object identity at write/cleanup and
native file/audit/state callback boundaries. Tests use fake peer/channel objects and local files;
published targets survive failed receives. Receive-close behavior is shared by existing GUI and
SDK endpoints. These checks do not establish remote publication acknowledgement, file-wire
checksums or clipboard no-echo. Publication confirmation and GUI reconnect tests are described below;
explicit clipboard lifecycle coverage is described below.

Native GUI wiring initially reproduces received bytes being sent back before the next local edit.
Immutable streamed receipts now suppress that echo and retain delayed/before-baseline local
edits without rehashing received paths. Tests cover empty/small/one-MiB receipts, immutability,
malformed metadata, selected-path restrictions, short-write/abort/truncation/publication failures,
relative cwd changes, callback replacement/clearing and ordinary/wrapped interruption behavior.
Actual native host/viewer channels converge with one local edit per side and exactly two
transfers, including a reply delivered before the first sender completes. GUI toggle integration
rejects stale viewer/engine/peer, stopped/auth-lost and live role-revoked receipts before watch I/O.
These are local fake-channel/controlled-loop checks; they do not establish loss recovery or remote
commit acknowledgement. Confirmed delivery and explicit reconnect/resume are covered below;
explicit clipboard lifecycle coverage is described below. No physical device or paid API acceptance is claimed.

The native bridge pair first reproduces dropped binary chunks being marked delivered even
though the remote target never appears. Publication-confirmed folder sends now leave that
digest pending, then retry and advance only after a matching atomic-publication receipt.
Controlled cases cover delayed end, empty/small/two-MiB transfer, corrupted chunks, checksum
rejection before target replacement, tampered size/hash, and stale acknowledgements under a
forced reused transfer ID with a fresh nonce. An old receipt cannot confirm a missing new target.
Fresh probes reject unsupported/version-mismatched or permission-revoked peers before sender
source metadata reads. Legacy manual sends still work against a non-confirming peer. Tests also
cover source cwd changes during negotiation, malformed/bounded envelopes, channel/control/stop
and permission-generation cancellation, loop replacement, single-producer ownership, weak
registry collection, wrapped original controls and completed-receipt/late-cancel ordering.
Actual GUI folder wiring requests confirmation and connected two-way native tests use it in
both directions. GUI reconnect/resume tests and explicit clipboard lifecycle coverage are described below.

The actual GUI stop/toggle path first reproduces failed/offline files being ignored when a new
engine establishes its initial baseline. Native paired channels now confirm both failed-send
retries and files created/edited while the viewer was disconnected, using a replacement viewer
and engine. Initial ignored files remain ignored; frozen received bytes retain subsequent edits.
Different host metadata, missing fingerprint, root, local user, user-store path or trusted role
cannot inherit prior pending data. Revoked/deleted owners fail before scanning, then explicitly
re-authorised retries retain pending data. Failed worker starts preserve that baseline too.
A real blocked polling sender remains owned through disconnect: an early handoff is refused,
late old work cannot send through the replacement, and a retry after retirement publishes the
pending file. Late old receipt callbacks cannot access/adopt either watch. Explicitly disabling
sync resets its baseline. Headless checkpoint tests cover immutability, no-I/O export/restore,
path/recursion matching, initial/recursive semantics and native filename validation. These are
controlled local filesystem/thread/fake-channel cases, without physical devices or paid APIs.
Explicit clipboard lifecycle and no-reflection coverage are described below.

Clipboard lifecycle reproduction initially shows buffered old text/images reaching a disconnected
or replacement viewer, stopped/unprivileged host clients writing the host clipboard, queued old
GUI deliveries changing native state and revoked GUI users retaining read/write permission.
Separate reproductions show text/image encoding adopting a new TCP/WS channel and revoked GUI
push reading the native clipboard. Fixes reject the original stale work while current deliveries
and deliberate repeated values remain valid. The controlled two-viewer host/SDK pair verifies
explicit text/image send/broadcast counts in TCP and WS viewer classes, with no automatic echo.
Offscreen Qt tests emit real queued callbacks from another thread and fake native change signals;
receiving never triggers push, while two deliberate identical pushes both send. Tests refresh
deleted/downgraded users, recheck peer changes during user-store access, preserve the registrant
instead of an ambient user, and recheck role changes between native read and send. Callback and
GUI boundaries preserve original wrapped controls; ordinary failures remain logged/contained.
A forced-GC-disabled offscreen regression requires a disconnected clipboard viewer
to disappear by ordinary reference release. Callback registration binds weakly once;
queued delivery retains its original peer/authority and cannot retarget a replacement.
Controlled TCP frame/input checks no longer leave their viewer panels waiting for GC.
This lifetime evidence does not by itself identify or accept the outstanding native crashes.
Existing loopback clipboard and GUI/registry/host-access cases remain passing. Controlled channels
do not claim new WS framing or real native-clipboard acceptance: framing has its existing tests,
native clipboard providers are replaced, and physical/paid acceptance stays deferred.
Managed task runtime
--------------------

Managed external/skill/local-model tasks have deterministic fake-target and loopback HTTP coverage.
Shared Python/AC/MCP/REST/CLI/GUI surfaces enforce task ownership and independent completion evidence.
Owned helper cancellation/deadlines, input cleanup and cross-database session exclusion have IPC-only
fixture coverage. Windows window/control scoping and redacted vision are implemented without native
acceptance. Physical activity detection and desktop/mobile acceptance remain open in Progress.md. A passive capability snapshot or configured timeout grants no authority.

Four managed workflow templates have deterministic fake-application and local HTTP/file coverage;
the local-files target also runs through a real owned helper without desktop input. Native application
acceptance remains deferred. Read-back mismatch and uncertain submission prevent automatic continuation.

Windows presence gating has synthetic hook-metadata, idle/lock/listener-loss and IPC takeover tests.
No native hooks were installed during acceptance. Other shared-desktop activity adapters remain open.
Persistent budget rollback/restart/regression handling and owner-scoped emergency stop have offline coverage.

Receipt review, non-effect retry, atomic history/journal linkage, image opt-in and owner-scoped 30-day
retention have fake-effect/cache coverage. These are persistence guarantees, not new native acceptance.
Cleanup preserves user outputs, external journal files and unrecognized cache content.

Preauthorized triggers have fake-source and real owned file-helper coverage for atomic deduplication,
restart, bounded pending work, owner revocation, authority-store isolation and event-scoped outputs.
Canonical-root symlink replacement is tested only where the filesystem grants symlink creation.
Emergency stop and queued recovery cover more than one thousand task records without native input.
