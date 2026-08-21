# What's New — AutoControl

## What's new (2026-08-21)

### Two Quality Gates That Had Been Standing Still

`Progress.md` carried an entry called "two thresholds we agreed to climb and
never did". Both were promises that lived only in a `pyproject.toml` comment,
with nothing anywhere that would ever move them. Both now have a mechanism.

**Coverage: the floor was 15 points below what the tests already earn.**
`fail_under = 35` was the first measured baseline and then never moved while the
suite grew past it. Every square of the nine-way matrix is over 50% — measured
on the run for PR #484, from 50.26% (ubuntu-22.04 / 3.10) to 51.69%
(windows-2022 / 3.14) — so CI would have passed a change that deleted a third of
the tests without a word. The floor is now **50**, taken from the lowest square
rather than from one machine, and the comment states the rule that was missing:
this is a ratchet, raised whenever the suite has earned it, not a target to
admire. 70 is still the destination.

**mypy: the scope was two directories, and could only ever grow by hand.**
The job checked `je_auto_control/api` and `je_auto_control/utils/failure_bundle`
— 4 files — while a comment promised the rest would join "the contract" later.
A scope written as a path list never grows on its own, and every new module
lands outside it by default.

So the scope is inverted. mypy now checks **the whole package**, and the modules
that do not pass yet are named in `test/verify/typing_contract_exempt.txt`.
**862 of 1,017 files are inside the contract today**, a new module is inside it
the moment it is written, and the list may only shrink:
`test/verify/typing_contract_verify.py` fails just as loudly when a listed
module starts passing (delete the line) as when an unlisted one stops. Both
directions were checked by breaking them.

**And it checks three platforms, not one.** mypy resolves `sys.platform`
branches against a single target, so the Ubuntu-only job never looked inside
the Windows, macOS or platform-gated code — three of the four backends. That
blind spot was real and is now measured: 13 modules fail only when the target is
Linux, 3 only when it is Windows. The script runs `win32`, `linux` and `darwin`
and unions the results, so the Windows and macOS backends are type-checked from
the Ubuntu runner.

**The part that took the work: the gate has to mean one thing.** A first
measurement taken on a dev checkout disagreed with a bare `pip install -e .`
about **38 modules** — 36 Qt modules that pass only because PySide6 is *absent*,
and 2 that fail only because `babel` and `pytest` are. Committing that list
would have reddened CI on arrival and mis-listed the other 36. A gate that flips
on `pip install` is not a gate, so every third-party module outside the base
dependency set is now forced to `Any`. `ignore_missing_imports` alone was not
enough — it still lets mypy read the real package when it *is* installed — and
neither was `follow_imports = "skip"`, which is silently ignored for `.pyi`
files: PySide6 ships inline stubs, so `follow_imports_for_stubs` was required
too. That is the same trap the numpy override in `pyproject.toml` had already
paid for and written down. A dev checkout with `[gui]` and `[webrtc]` and a
clean base install now produce identical results.

The remaining modules cluster — `utils/remote_desktop` (13), `gui` (11) — and
`Progress.md` records clearing them one cluster at a time. The first cluster is
below.

### The Platform Seam Now Says What a Backend Is

`wrapper/platform_wrapper.py` is the Strategy hub: it imports exactly one
backend and re-exports eight names, and everything above it is written against
those names rather than against a platform. Nothing said what they *were*.

Measured, that had two consequences, and neither was theoretical:

- **mypy bound every name to the Windows backend, on every target.** The
  branches are `if is_windows() / elif is_macos() / …`, which a type checker
  cannot resolve, so it read all of them and kept the first — so the layer above
  the seam was checked against Win32 signatures even when the target was Linux
  or macOS, and it reported "`recorder` has type `OSXRecorder`, expected
  `Win32Recorder`" for the *correct* code on the way past.
- **A backend could omit a member and nobody would say so** until a call site
  three layers up failed on the user's machine.

The eight names are now declared before the branches bind them, three of them
with protocols in the new `wrapper/backend_contract.py` — `ScreenBackend`,
`KeyboardCheckBackend`, `RecorderBackend` — and each `_platform_*` assembly
module annotates what it assigns. A backend that does not answer the seam's
questions now fails in its own file, naming the missing member. That is not
hypothetical either: turning it on immediately reported that the Windows
`screen.size()` returns a `list` where the other three backends return a
`tuple` and where the public `screen_size()` promises a tuple. Fixed, and every
caller only ever unpacked the two values.

`keyboard` and `mouse` stay `Any`, which is what mypy had already inferred for
them: macOS takes `is_shift` on `press_key` and orders its mouse calls
`(x, y, button)` where Windows and X11 take the button alone, and a Windows
mouse "keycode" is a tuple of three event flags where the others are an int.
One protocol cannot describe both, and `Progress.md` carries what it would take.

Clearing the cluster fixed four bugs the types had been hiding, all of the same
shape — a value that could be `None` reaching something that could not take one.
They are listed in `CHANGELOG.md`. Along the way four modules outside the
cluster (`utils/cv2_utils/screen_grabber`, `utils/executor/mouse_aliases`,
`utils/pytest_plugin/keywords`, `utils/vision/vlm_api`) went green on their own:
they had been failing on the seam's accidental types, not on their own code.
**145 modules left, 872 of 1,017 files inside the contract.**

Re-measuring `architecture_explore.md` for this change turned up one row the
measuring tool had never been able to read: §8's `wrapper/` row carried prose
in its 行數 cell, so it parsed as a one-column row — the tool wrote the *line*
count into the 檔案數 column, and left the directory out of the named subtotal,
which meant 其餘模組 counted it a second time. The row is now two plain numbers
(19 files, 3,293 lines), the note it was carrying has moved to §5.2 as the
`wrapper/window_backends/` row that section had been missing entirely, and
其餘模組 no longer double-counts 3,293 lines.

## What's new (2026-08-20)

### Three Tests That Had Been Skipped Since They Were Written

`test_r3_gui_thread_marshal.py` carried three `@pytest.mark.skip`s whose own
reason said what they needed: *"needs subprocess isolation (see
test_actions_menu_gui) … skip until then."* They covered real wiring — that a
file received on a WebRTC worker thread reaches the GUI thread through a
queued signal rather than a thread-affine `QTimer.singleShot`, and that the
admin console's thumbnail poll deletes its `QThread` each tick instead of
leaking one per interval.

Skipping them was the right call at the time: building the WebRTC panel or the
admin console and then tearing a worker `QThread` down aborts the *shared*
pytest process under offscreen Qt. Because `deleteLater` is a no-op until an
event loop runs, the abort does not even land in the test that caused it — it
detonates inside some later, unrelated file, with no traceback.

**They now run, in their own process.** One probe performs all three checks,
writes a JSON verdict per check, and `os._exit(0)`s without teardown — the same
shape `test_actions_menu_gui` has used for the full tab set. Each verdict is
`ok`, `failed: …` or `unavailable: …`, so a machine without the `[webrtc]`
extra (CI's `pytest-headless`, among others) reports a skip rather than a
failure, while a machine that has it actually checks the wiring.

The checks have teeth, which was verified rather than assumed: deleting the
one line `thread.finished.connect(thread.deleteLater)` from
`admin_console_tab.py` turns the third verdict into `failed: the QThread
outlived finish`, and leaves the other two green.

The headless suite now runs end to end with no `--ignore` flags — 4,815
passing, and the only remaining skips are optional-dependency and
platform gates. No "skip until then" is left in it.

### Windows arm64 Was Never a Code Problem

The entry for this said `BLOCKED`, and that was half right. Two dependencies
publish no `win_arm64` wheel and still do not: `opencv-python` has none in any
version, and `cryptography` stopped at 46.0.3 while this project's floor of
`>=48.0.1` is a security floor (GHSA-537c-gmf6-5ccf) that cannot be lowered.
So `pip install` fell back to building OpenCV from source, CMake could not
configure for ARM64, and twelve minutes later the runner failed. That much was
measured, and it is why the runner left the matrix.

What was not measured is the half that mattered. **Nothing in the package
needs either wheel at import time.** Blocking `cryptography`, `cv2`,
`je_open_cv`, `numpy` and `PIL` in a subprocess, `import je_auto_control`
still binds all 1,238 public names, and the executor, the MCP tool registry,
the CLI, `api.generate_code` and `api.create_failure_bundle` all import and
run. The blocker lived entirely in `pyproject.toml`'s dependency list.

**So the fix is a marker, not an architecture.** Three requirements carry
`sys_platform != 'win32' or platform_machine != 'ARM64'` — `opencv-python`,
`cryptography`, and `je_open_cv`, which is pure Python but depends on OpenCV
and would otherwise drag it back in through the side door. Pillow is
deliberately not marked: it has always shipped `win_arm64` wheels and the
earlier note calling it a blocker was a guess. `windows-11-arm` is back in
`platform-smoke.yml`, on 3.14 only, because CPython's official Windows arm64
builds start at 3.11.

**What Windows arm64 gives up is now said out loud, in the error itself.**
`find_image*`, the OpenCV `screenshot()`, the secret vault, action-file
encryption, ACME/TLS and encrypted recording raise a message naming the
missing wheel and the platform, instead of a bare `ModuleNotFoundError` that
reads like a broken install. Two new accessors in
`utils/cv2_utils/optional.py` cover the two doors every image path goes
through; the other seventy-odd lazy `import cv2` sites are left alone on
purpose, because wrapping them buys the caller nothing it can act on.

A deliberately unglamorous test guards the whole thing:
`test/unit_test/headless/test_arm64_dependency_markers.py` reads
`pyproject.toml` and evaluates the marker against five platforms, so removing
it — or "tidying" Pillow into it — fails loudly rather than costing an arm64
user a working feature.

### The Platforms This Project Claims, Now Measured

The suite ran on `windows-2022` alone for its whole life, plus one Linux
container run. macOS got two commands and nothing else. Wayland had five jobs
reading input back off a real peer; X11 — the older and more widely deployed
of the two Linux paths — had none, and every X11 assertion in the suite was
made against a mock of `python-Xlib`.

**The suite now runs where the project says it runs.** `pytest-headless`
became an OS matrix: Windows keeps all five Pythons, Linux and macOS carry the
two ends of the range. Linux runs under a real Xvfb rather than Qt's offscreen
platform, because the X11 backend opens a display at import time and offscreen
would hide exactly the breakage this exists to find. It found two real macOS
defects on the first run:

- `write("\b")` had no key route on macOS, so it fell through to the space
  fallback and typed a space where a backspace was asked for. X11 and Wayland
  both carry the raw character; macOS was the one that did not.
- `system_profiler` reports a *symbolic* vendor id for Apple's own devices —
  `apple_vendor_id`, not a number — and that went straight into a field
  documented as four hex digits. Its leading `a` is a valid hex digit, so a
  lenient parse turns it into `000a`.

**X11 input is read back out of a real client.** A new `x11-verification` job
runs against a real Xvfb server with a real window manager, taking ground
truth from other codebases than the subject: `xev`, a real X client that
prints every event delivered to its window; ImageMagick's `import` against a
root painted two asymmetric colours; `xdotool` and `xdpyinfo`. The assertion
worth naming is `synthetic NO` — `XSendEvent` traffic arrives with `YES` and
is discarded by most toolkits, so a backend that quietly stopped driving real
input would still pass any check that only counted events.

**macOS turned out to be fully testable in CI, contrary to the usual
assumption.** A `macos-14` runner grants *both* Screen Recording and
Accessibility: capture returns real pixels rather than the black rectangle a
refusal produces, `CGEventPost` moves the cursor and the move reads back
exactly, and the AX walk returns real elements. That was measured first and
asserted second, and the probe still refuses to pass while its expectations
table is empty.

### Five Errors That Every Boundary Missed

The exception hierarchy is flat so that the executor, the poll loops, the
request handlers and the GUI slots can each contain the whole family in one
`except`. Round 3 reparented the family for that reason; five classes were
missed, and one of them was reachable from an action list.

`AC_config_import` with a malformed bundle raised `ConfigBundleError`, which
inherits `Exception` directly, so the executor's per-action clause — which
lists `AutoControlException` and the builtins — did not catch it. The error
went past the boundary and took every remaining action with it, under
`raise_on_error=False`, where the contract is that a failed action is
*recorded*. Measured, not reasoned: a two-action list lost its second action.
`AC_usb_remote_devices` and `AC_usb_remote_open` had the same path through
`UsbClientError`.

All five now derive from `AutoControlException`. What keeps the next one out is
not a list of the five: `test_exception_family_is_flat.py` walks the package
with `ast` and fails on *any* class inheriting `Exception` directly, against a
three-entry allowlist that has to state why. `LoopBreak` and `LoopContinue` are
on it because they are control flow — a family handler swallowing a `break`
would be the mirror-image bug — and the MCP dispatcher's private error carrier
because it never leaves the dispatcher that raised it. The allowlist is checked
in both directions, so a stale entry fails too.

### A BSD Found the Same Mistake in a Second Place

The FreeBSD VM was added to prove the X11 backend drives a real BSD. It failed
before it got there, and what it failed on was not a wheel: **FreeBSD's
`python311` has no `sqlite3`.** The module is in the standard library but not
in every build of it — CPython links it against a system library, and FreeBSD
packages the result separately as `databases/py-sqlite3`.

Ten subsystems imported it at module scope: run history, checkpoints, the work
queue, agent memory, the remote-desktop audit log, SQL data sources, and the
`except` tuples that keep a database error from killing the REST handler
thread, the chat-ops poll loop and the MCP transport. Every one of them is
reachable from the facade, so `import je_auto_control` failed outright — on a
machine where moving a mouse needs no database at all. This is the same shape
as the OpenCV/Pillow finding one commit earlier, from a source that reasoning
about wheels would never reach: the standard library is not the same size on
every platform.

**The ten now go through `je_auto_control/utils/sqlite_support.py`.**
`require_sqlite3()` returns the module or raises
`AutoControlUnsupportedOperationException` — deliberately the type the platform
backends already raise for something they cannot do, so the GUI tabs, the REST
handler and the executor report "not available here" instead of dying on an
`ImportError` that none of them catch. `SQLITE_ERRORS` and
`SQLITE_OPERATIONAL_ERRORS` are tuples rather than classes, so
`except (ValueError, *SQLITE_ERRORS)` stays a valid handler that catches
exactly the right amount — nothing — where nothing can raise them.

That left one thing still opening a database during import: `HistoryStore`
connected in its constructor, and `default_history_store` is built while the
facade is importing. It connects on first use now, which is also why
`import je_auto_control` no longer creates `~/.je_auto_control/` as a side
effect of being imported.

Three things keep it fixed. `test_sqlite_is_optional.py` blocks `_sqlite3` in a
subprocess — exactly what FreeBSD reports — and requires the facade to import
anyway, with the error tuples empty. The FreeBSD job asserts the module is
*absent* on the VM, so a future image that happens to ship `py311-sqlite3`
turns the job red rather than quietly retiring the property it was added to
test. And `run_diagnostics()` lists `sqlite3` among the optional dependencies,
so an operator sees the gap as a line in a report instead of a traceback.

### The macOS Recorder Was Written, Unreachable, and Wrong

`OSXRecorder` had been a complete implementation for as long as
`wrapper/_platform_osx.py` had said `recorder = None`, and that was not an
oversight. The listener called `NSApplication.sharedApplication()` **at import
time**, and stopping a recording meant `AppHelper.runEventLoop()` — a loop
that never returns to its caller. Wiring it up would have put both on the path
of `import je_auto_control`, which is a regression, not a fix. So `record()`,
`stop_record()` and `je_auto_control record` all refused on macOS with
"Cannot use recorder on macOS", and the capability matrix said `unavailable`.

**The premise was wrong: a `CGEventTap` needs a run loop, not an
application.** Create the tap on a dedicated thread, add its source to *that*
thread's run loop, and pump the loop in short `CFRunLoopRunInMode` slices so a
stop flag is honoured between them. Nothing touches AppKit, nothing runs at
import, and `record()` returns immediately. The macOS hotkey backend had been
driving a tap exactly this way in the same tree the whole time.

The tap is **listen-only**, which is load-bearing rather than a detail: a
recorder that consumed events would swallow the very input it is recording, so
the user's clicks would stop working the moment recording started.

Two defects were sitting in that code, and only a Mac could show either:

- **Recorded clicks were mirrored vertically.** Coordinates came from
  `NSEvent.mouseLocation()`, whose origin is the **bottom-left** of the
  display, while every replay posts into the top-left space `osx_mouse` uses.
  A click recorded near the top of the screen replayed near the bottom, with
  no error anywhere — the same silent shape as `write("\b")` typing a space.
  It reads `CGEventGetLocation` now, which is already the replay's space.
- **Modifiers were not recorded at all.** macOS sends no key-down for Shift,
  Control, Option or Command; it sends one `flagsChanged` event carrying the
  new flag set. A recording therefore could not say a modifier was held across
  the actions that followed — which is one of the two reasons the timeline
  exists. They are reconstructed from the flag bits now.

**The half that is not platform-specific stopped being copied.** Everything
after the capture — the down-events-only queue the executor is handed, the
`delta_ms` timeline a replay consumes, the mouse-only and keyboard-only
filters — is one implementation in
`utils/input_macro/recorder_base.py`, and both backends subclass it. A second
hand-written copy of that shaping would have diverged silently, and the way it
would surface is a recording made on one OS replaying wrongly on the other.

**And the recording had nowhere to go.** Verifying the new backend end to end
turned up a defect that was never macOS-specific: `replay_timeline`'s dispatch
table held the `run_sequence` DSL's vocabulary — `press`, `click`, `key` —
while every recorder emits its own — `key_down`, `mouse_up`, `scroll`. The two
sets were **disjoint**. So `stop_record_timeline()` handed to
`replay_timeline()`, which is the pipeline the docstrings and the
`ac_record_stop_timeline` tool description both prescribe, matched no handler
at all: it replayed an empty session and returned the full event count as
played. The one op that did match, `scroll`, read a key the recorder does not
write, so it fell back to a single notch in the default direction. Both are
fixed, on every platform.

**It is verified on a real window server, not against a fake.** The
`macos-capabilities` job posts a move, a click and a keypress through the
public API while recording, and asserts they come back out of the tap with the
release and with the coordinates they were posted at. Decoding is unit-tested
separately against genuine `CGEventCreate*` events, which needs no
Accessibility grant — so the parts that can be tested without a permission
are, and the one part that cannot is where the permission is measured.

### Window Management Is No Longer Windows-Only

It was: the facade branched on `sys.platform` and raised everywhere else,
leaving 23 `AC_*` commands and their MCP tools dead on macOS and Linux. It now
goes through a backend seam — Win32, EWMH over `python-Xlib` on X11, Quartz
plus the accessibility API on macOS, and a null fallback that lists nothing
and refuses actions with a reason.

Two things only a real window manager could show up were wrong first time:

- **The rectangle is the frame, not the client.** Win32's `GetWindowRect`
  returns the frame, and every caller is written against that, so reporting
  the client area was off by the decorations on X11 alone — silently, and by
  a different amount per window manager.
- **A move has to go through `_NET_MOVERESIZE_WINDOW`.** Under a reparenting
  window manager a client's own x/y are relative to its frame, so a direct
  `ConfigureWindow` asks in the wrong coordinate space. Asking openbox for
  (300, 220) that way landed the window at (302, 260).

Refusals now raise a class that is both an `AutoControlException` and a
`NotImplementedError`. The GUI tabs and the REST handler already catch the
latter to say "not on this platform"; the executor catches the former, and a
bare `NotImplementedError` slipped past every containment boundary — aborting
a whole script where one action should have been reported as failed.

### Linux Has an Accessibility Backend

It had none — the selector fell through to the null one while the capability
matrix claimed "backend tests" for Linux X11. The new backend speaks
**AT-SPI2**, which is a D-Bus protocol rather than a library, and that is what
makes it reachable without a new dependency: `pyatspi` and
`gi.repository.Atspi` are distribution packages built against the system
introspection data and cannot be installed into a virtual environment.

The D-Bus client written for the portal handshake moved from `linux_wayland/`
to `utils/dbus_client/` to make that possible, and verifying the backend
against a real bus and a real GTK application immediately found a gap in it:
**it could not demarshal signed integers.** The portal never needed one, and
AT-SPI reports a component's extents as four *signed* values, because a window
on a monitor left of or above the primary one is at a negative coordinate — so
the backend could read a tree but not where anything in it was.

Because AT-SPI is a bus rather than a display protocol, this is the one
capability where Wayland is not the restricted case: the same bus serves both
Linux sessions.

### The BSDs, and arm64

`platform_wrapper` refused to start on anything that was not
win32/cygwin/msys, darwin or linux/linux2, and each of the seven X11 backend
modules carried its own copy of the same Linux-only guard — so a FreeBSD,
OpenBSD or NetBSD desktop, which runs the same X server and the same
`python-Xlib`, could not import the package at all. `sys.platform` was being
compared against literal lists in over a hundred places, so the fix is one
place that decides: `utils/platform_id`, whose `is_x11_unix()` asks the
question those guards were always trying to ask.

A `freebsd` job boots a real FreeBSD 14 VM inside the runner. It could at
first only check the *decision* — that `sys.platform` really reads `freebsd14`,
and that the classification every relaxed guard asks answers correctly on it —
because importing anything under `je_auto_control` ran the facade, and the
facade imported OpenCV and cryptography at module scope. `utils/platform_id`
had to be loaded by file path to get even that far. See below: that turned out
to be the wrong thing to work around, and the job now drives the whole backend.

`ubuntu-22.04-arm` joins the smoke matrix and passes; `macos-14` was already
arm64. (**Superseded the same day** — see "Windows arm64 Was Never a Code
Problem" at the top of this file: the runner is back, because the blocker
was the dependency list rather than the code.) `windows-11-arm` was tried
and removed, and re-measuring turned up a
**second** blocker the first pass had missed: opencv-python publishes no
`win_arm64` wheel in any version, and cryptography stopped publishing one after
46.0.3 — while this project's floor is `>=48.0.1`, a security floor
(GHSA-537c-gmf6-5ccf) that cannot be lowered to reach a wheel. Pillow, named
alongside OpenCV in the original entry, ships `win_arm64` wheels and was never
part of the problem. None of that needs an arm64 machine to check: `pip
install --dry-run --only-binary=:all: --platform win_arm64` answers it in
seconds, and `Progress.md` records the command next to the finding.

### The Facade Insisted on OpenCV to Move a Mouse

`Progress.md` recorded the missing BSD coverage as needing "a machine with the
dependency set on it, not a different CI trick". That entry was making the
mistake its own Wayland section warns about three lines further up: **asking
what the environment could not do, instead of asking who actually could not do
it.** It was not FreeBSD that could not run the X11 backend. It was this
package, which imported five image and crypto wheels before it would let you
move a pointer.

The measurement was small. Ten modules on the facade's import path pulled in
OpenCV, NumPy, Pillow, `je_open_cv` or `cryptography` at module scope, across
about sixty call sites — while most of `utils/` had been importing OpenCV
lazily all along, with the docstrings to say so. Those ten now do the same. The
type annotations that referenced Pillow moved under `TYPE_CHECKING`, and the
two public `ImageSource` aliases keep Pillow in the union as a forward
reference, so nothing changes for a caller or a type checker.

What `import je_auto_control` needs now is `defusedxml`, plus `python-Xlib` on
an X11 platform. Both are pure Python. The heavy five are still hard
dependencies and still install by default; the difference is that a platform
with no wheel for them can now use the half of the package that never needed
them. `test/unit_test/headless/test_facade_import_is_light.py` blocks all five
in a subprocess and imports the facade anyway, because this is a property one
convenience import silently undoes and every runner with wheels keeps passing.

### The BSD Job Drives Real Input Now, and Found the Defect That Was Waiting

With the facade light, the FreeBSD VM needs python-Xlib, defusedxml and an X
server — an install measured in seconds, where the ports build for OpenCV had
not finished after fifty minutes. So `test/verify/freebsd_verify.py` runs the
backend rather than the guard, and takes its ground truth from the X server
answering for itself: `query_pointer` for where the cursor is, its button mask
for which buttons the server believes are down, and `query_keymap` — the bitmap
of every physically-held key — for whether an injected key press really landed.
That last one is why no second process is needed here; the Linux
`x11-verification` job already reads events back out of `xev`, and what a BSD is
uniquely needed to answer is whether this code drives the same server on a
different kernel.

It also maps a real X window that has asked for button events, because one
defect could not be caught any other way: **`mouse_scroll` did nothing at all
on a BSD.** It matched Windows, then macOS, then a literal
`["linux", "linux2"]` — one of the hundred-odd hand-written platform lists
`platform_id` exists to replace, and one that had been missed — so a BSD caller
fell off the end of the chain with no backend call, no exception and no log
line. A wheel event never shows up in the pointer mask, since X11 delivers a
scroll as a press *and* release of button 4/5/6/7 too fast to sample, so only a
client reading the event queue can see it happen or not happen.

### `mouse_scroll` Means the Same Thing on Every Platform

This had been sitting in `Progress.md` as a `DECIDE`, and the maintainer
settled it: **the sign of `scroll_value` reverses the direction everywhere, and
`scroll_direction` names the direction a positive count takes.**

Windows and macOS had always read the sign. X11 encodes direction as a button
rather than a signed delta, so it took the direction from `scroll_direction`
and discarded the sign — deliberately, because a negative count used to make
`range()` empty and scroll nothing at all. The cost was portability with no
symptom to debug: `mouse_scroll(-3)`, written and tested on Windows, scrolled
three notches *down* on Linux instead of up. Wayland had the same `abs()` in
`_wheel_deltas` and the same result.

Both now turn a negative count back into the opposite direction — a button swap
on X11, a sign on the Wayland delta. `docker/x11_verify.py` pins it against a
real X server through `xev`, `freebsd_verify.py` pins it on a BSD, and
`test_scroll_sign_is_portable.py` pins it on every runner without needing a
display. The migration note for anyone who was relying on the magnitude alone
is in `CHANGELOG.md`.

### The Destructive-Action Prompt Reached Only One of the Two Transports

`JE_AUTOCONTROL_MCP_CONFIRM_DESTRUCTIVE=1` is documented as gating *every*
destructive MCP tool behind a confirmation prompt, with one stated caveat: the
client has to advertise the `elicitation` capability. Measured against a real
`HttpMCPServer` with a real destructive tool, the gate fired on stdio and
**never fired over HTTP** — not in any of the four combinations of plain POST
or SSE, one connection or two.

Two independent reasons, and the second is why keeping the connection open did
not help. A plain `POST` is one request and one response, so its connection
scope had no server→client channel and the prompt had nothing to travel down.
An SSE `POST` did have one, but `_dispatch_sse` sets `close_connection`, so the
scope keyed on that TCP connection was forgotten before the next request — and
the `elicitation` capability advertised at `initialize` went with it. The call
then took the "client cannot be prompted" branch, logged one INFO line, and ran
the tool. An operator who set that variable on an HTTP-exposed server was
getting no confirmation at all.

**The transport now has the identity MCP actually specifies.** `initialize`
mints an `Mcp-Session-Id` and returns it as a response header; a client that
echoes it keeps one dispatcher scope across every connection it opens. `GET`
with `Accept: text/event-stream` opens the standing server→client stream that
server-initiated traffic belongs on, and answering a server request is an
ordinary `POST` matched back to the waiting call by id. `DELETE` terminates.
The dispatcher itself needed no change — it already scoped capabilities and
active-call slots on an opaque `connection_id`, so a session id simply takes
that slot, and the per-connection isolation guarded by
`test_r3_mcp_connection_isolation` is preserved verbatim: a session is just an
identity that outlives a socket.

So the confirmation now round-trips over HTTP, and the test that proves it uses
four separate connections — one that initialized, one holding the stream, one
carrying the `tools/call`, one carrying the decline — none of which shared a
socket with the handshake. Declining blocks the tool; accepting runs it.

Measuring it turned up a second way through that was worth pinning: an SSE
`POST` carrying a session id needs no standing stream at all, because its own
response stream is already a server-to-client channel. The `elicitation/create`
goes out ahead of the result on the same socket the call arrived on. Both paths
now have a test.

What did *not* change is the fallback: a client that ignores the session header,
or that only ever sends plain JSON `POST`s with no stream open, has given the
server nowhere to ask, and its destructive calls still proceed — exactly as they
do for a stdio client that never advertised `elicitation`. That is now a
documented boundary with a test on each side of it rather than an accident — but
it is still a boundary, so the bearer token, the `127.0.0.1` bind and
`JE_AUTOCONTROL_MCP_READONLY` remain the controls that do not depend on the
client behaving.

Sessions are bounded in both directions: swept after ten minutes untouched, and
the registry evicts the least recently seen once it holds 128. Dropping a
session — however it goes — releases the dispatcher state held under its id,
which is the same release a closing socket used to perform, moved to the
identity that actually owns that state. Because every `initialize` mints a
session, including for the many clients that ignore the header and never come
back, evicting one that was never used after its handshake is logged as routine;
the warning is saved for evicting a session someone was holding, which is the
one that means the cap is too low.

The new refusals also exposed an old assumption in the transport. Every `4xx`
runs `_drain_body()` first, so the client can read the response before the
socket closes — but the new unknown-session `404` and duplicate-stream `409` are
decided *after* the body has been parsed, and so was the pre-existing "body must
be UTF-8" `400`. The drain then went looking for bytes that were already gone
and blocked until the thirty-second read timeout, pinning that worker and
printing a `ConnectionAbortedError` traceback whenever the peer closed first.
It now skips the drain once the body is consumed, and treats a peer that has
already vanished as nothing left to be courteous to.

## What's new (2026-08-19)

### Two Wayland Judgement Calls, Settled

Two items had been sitting in `Progress.md` marked `DECIDE`: not missing work,
missing decisions. They turned out to be the same problem twice — a compositor
setting the library can *measure* but cannot *read*, and therefore must stop
pretending to know.

- **Pointer acceleration is now something the operator declares, and the
  library believes.** The measurement stands: `ydotool mousemove --absolute`
  sends relative motion, libinput's default adaptive profile doubles it, and no
  client can read the factor back. What was undecided was what to do about it —
  keep warning and move anyway, refuse outright, or let the operator say.
  Refusing outright would have taken `set_position` away from every Wayland
  machine without `liboeffis`, so the answer is a declaration:
  `JE_AUTOCONTROL_WAYLAND_POINTER_ACCEL=flat` means acceleration is off for the
  ydotoold device, and the move goes out silently and exactly; `=strict` means
  refuse the move rather than let a click land somewhere else; unset keeps
  today's warn-once-then-move, so nothing that works now stops working. An
  unrecognised value falls back to the warning *and says that it did* — a typo
  in a shell profile must not quietly promote a move to trusted-exact. The
  whole gate is on the ydotool path; libei is absolute at the protocol level.
- **The software cursor in a Wayland capture is documented, not worked
  around.** `seat-verification` measured it in passing: no capture in this
  project passes `grim -c`, so none asks for the pointer, and the pointer is in
  the image anyway. The reason is not ours — wlroots draws a *software* cursor
  whenever the backend has no cursor plane, and a software cursor is composited
  into the output buffer, which is exactly the buffer `wlr-screencopy` hands
  back. Headless is permanently in that state; so is any real desktop running
  `WLR_NO_HARDWARE_CURSORS=1`. Windows' BitBlt and the X11 path never include
  the pointer, so this is a Wayland-only inconsistency, and with the pointer
  resting on its target a locator, a template match or an OCR read sees a
  pointer-shaped hole in the middle of it. Both ways out — move the pointer
  away and back, or mask around it — need to know where the pointer is, and
  Wayland does not let a client read that; an in-process guess goes stale the
  moment the user touches their own mouse, and masking the wrong place is worse
  than a visible cursor. So it is written down instead: in the capability
  matrix, in all three READMEs, and in the diagnostics bundle, where the
  `screen_capture` check now carries `cursor_may_be_captured` so the report
  that explains a failed locator names the reason. `seat-verification` asserts
  the behaviour as measured, so if wlroots ever honours `overlay_cursor` for
  software cursors, CI goes red and tells us.

### A Compositor That Consumes Input Was Three Environment Variables Away

`ydotool mousemove --absolute` is not absolute. It emits no absolute event:
it sends `INT32_MIN` on both axes to drive the cursor into whatever corner the
compositor clamps to, then sends the target as a relative displacement. What
that corner *is*, and what the compositor does to the displacement on the way,
were the last two open questions on the Wayland input path — and both were
recorded as needing a VM running a desktop that consumes libinput devices.

- **They needed no VM.** wlroots takes `WLR_BACKENDS=headless,libinput`: the
  outputs stay virtual while the input half is the real libinput backend.
  libseat's builtin backend opens the devices without logind, and
  `SEATD_VTBOUND=0` stops it reaching for a VT no container owns. The fourth
  requirement is the one that is easy to miss — libinput enumerates through
  udev rather than through `/dev`, so `systemd-udevd` has to be running before
  ydotoold creates its device. With those four in place, ydotoold's uinput
  device is an ordinary seat device, and `grim -c` composites the cursor into
  a screenshot, so the compositor answers in layout coordinates.
- **The corner is the layout's top-left, not layout `(0, 0)`.** Those are the
  same point only while every output sits at a non-negative position. On the
  layout every desktop with a monitor left of the primary one has, they differ
  by the layout origin — so on a `-1280` layout an untranslated request for
  layout `(0, 0)` put the cursor on the *other monitor*, 1,280 pixels away.
  `mouse.set_position` now subtracts `layout_origin()` before handing the
  coordinate to ydotool, which is the same correction the capture path already
  applies; the lookup both input paths share moved into
  `linux_wayland/_layout.py` so libei and ydotool cannot drift apart on it.
- **And pointer acceleration scales the rest.** The displacement is relative
  motion, so libinput accelerates it: measured against a real wlroots session,
  the default adaptive profile lands the cursor exactly twice as far from that
  corner as asked, because `--absolute` sends both of its events in one frame
  and the velocity saturates the profile. With `accel_profile flat` and
  `pointer_accel 0` the same call is pixel-exact. ydotool's own `--help` has
  said "You need to disable mouse speed acceleration for correct absolute
  movement" all along; the backend now logs that caveat once per process
  instead of letting a click land silently in the wrong place. Nothing else
  can be done from inside the library — the factor is the compositor's
  setting, not something a caller can read back.
- **A new `seat-verification` job holds all of it.** `docker/Dockerfile.seat`
  runs the two layouts the capture image runs, and 14 checks each: that sway
  really is holding the ydotool device, that `--absolute (0, 0)` draws the
  cursor flush into the layout's first pixel, that with acceleration off the
  move is one pixel per pixel, that an untranslated `(0, 0)` misses the
  monitor it names, that `set_position` subtracts exactly the origin and lands
  on the pixel it was given on both monitors, and that the acceleration factor
  is the 2x this was measured at. Nothing in it depends on the cursor theme:
  every claim is a difference between two captures, which the image's offset
  from its hotspot cancels out of.
- **One thing it found on the way.** On this compositor a `grim` capture that
  asks for no cursor overlay contains one anyway, because wlroots draws a
  *software* cursor whenever the backend has no cursor plane — always on
  headless, and on any session where the driver refuses one or the user set
  `WLR_NO_HARDWARE_CURSORS=1`. Every locator, template match and OCR read goes
  through that capture, so the pointer punches a pointer-shaped hole in
  whatever it is sitting on. The check records the behaviour as measured, and
  the decision was to document it rather than work around it — see the
  capture section below.

### The Screen-Capture Portal Could Never Have Worked, and a Real Bus Said So

- **`xdg-desktop-portal` answers with a signal directed at the connection that
  called it.** `Screenshot` returns a *request handle*, not an image; the image
  arrives later as `org.freedesktop.portal.Request::Response`, addressed to the
  caller's unique bus name. The bus routes a directed message to its
  destination and nowhere else, so no match rule on any other connection can
  make it arrive somewhere else.
- **The old implementation was two connections.** It started `gdbus monitor` in
  one subprocess, made the call from a second `gdbus` invocation, and read the
  monitor's stdout with a pair of regular expressions. Each `gdbus` invocation
  opens its own connection under its own unique name, so the process listening
  was never the process addressed. Measured against a real `dbus-daemon`: the
  monitor sees the call go past and prints nothing else, and the capture runs
  out its full 30-second timeout, every time. The only listener that can see a
  directed signal is a full bus monitor — `dbus-monitor`, which asks the bus
  for `BecomeMonitor` — and needing permission to observe every message on the
  user's session bus is a poor price for a fallback screenshot.
- **The tier now speaks D-Bus itself, on one connection.**
  `linux_wayland/_dbus_client.py` is a session-bus client in the standard
  library alone: connect, SASL EXTERNAL authentication, `Hello`, `AddMatch`,
  one method call, then read until the matching signal arrives. It is
  deliberately not a general binding — no properties, no introspection, no
  object export, no descriptor passing (liboeffis still does the one call that
  needs that). `portal.py` subscribes to the request path it predicts from its
  own unique name *before* it calls, and follows the returned handle as well
  when a portal ignores `handle_token`.
- **Which also removes a dependency rather than adding one.** The tier used to
  need `gdbus` (glib2) installed; it now needs nothing but a session bus, so
  the last-resort capture path is available on strictly more desktops than
  before. The install hint and the diagnostics check say so.
- **Verified end to end on a real bus.** A new `portal-verification` job runs a
  real `dbus-daemon`, a real portal implementation and the real client: the
  capture comes back as PNG bytes that decode to the pixels the portal painted,
  at a percent-escaped path with a space in it, and the portal's file is gone
  afterwards. Every way a portal ends without an image is driven too — a
  dismissed dialog, a dialog left open, a success carrying no URI, a URI that
  is not a local file — and each has to fail closed on AutoControl's own clock.

### The RemoteDesktop Portal Handshake Never Needed a GNOME VM Either

- **The portal is a D-Bus interface, not a compositor feature.** Reaching libei
  on GNOME and KDE means `CreateSession` → `SelectDevices` → `Start` →
  `ConnectToEIS`, ending in an EIS file descriptor passed over the bus. That
  was recorded as unverifiable without a GNOME VM because
  `xdg-desktop-portal-wlr` implements ScreenCast and Screenshot but not
  RemoteDesktop — which confuses "no container ships one" with "no container
  can host one". Whatever owns `org.freedesktop.portal.Desktop` and answers
  those four calls *is* the portal, as far as `liboeffis` is concerned.
- **So the verification owns the name itself.** `docker/portal_server.py` is a
  real D-Bus service on a private session bus, and its `ConnectToEIS` hands
  back a live connection to the same real `libeis` server the `eis` image uses.
  The real `liboeffis` runs the real handshake; the descriptor that comes out
  carries a real EI session; and the key presses, absolute motion and button
  edges emitted through it are recorded by an independent implementation at the
  far end.
- **What it settles.** That the four calls arrive in the prescribed order at the
  request paths the client predicted; that `SelectDevices` is asked for keyboard
  and pointer and nothing wider, so the grant a user consents to is the one this
  backend needs and `OEFFIS_DEVICE_DEFAULT` is not the `= 0` all-devices
  sentinel; that the descriptor is a live socket the caller owns and must close,
  which is what makes handing it to `ei_setup_backend_fd` — a function that
  takes ownership — correct rather than a double close.
- **And every refusal.** A dismissed consent dialog, a dialog left open, a
  withheld descriptor, a session the portal closes, a portal too old to have
  `ConnectToEIS` at all, and no portal on the bus: each has to come back as a
  refusal on this project's own clock rather than a hang or a silent downgrade.
  The `OEFFIS_EVENT_CLOSED` branch had never had a peer able to drive it; it
  does now.
- **What is still not claimed.** The consent dialog as a dialog. Nobody
  dismisses anything in CI, so what a real mutter dialog looks like, and how
  long a real person leaves it open, stays mutter's business. What a dialog
  *produces* — a grant, a refusal, silence — is all exercised.

### One Packaging Fact That Was Recorded Wrong

- **Debian trixie does ship `liboeffis`.** `Progress.md` said it did not, and
  concluded that the libei fast path was effectively off across Debian and
  Ubuntu. Measured: `liboeffis1` 1.3.901-1 is in trixie/main, providing
  `liboeffis.so.1`. What is true, and what actually matters to a user, is that
  it is a *separate binary package* which `libei1` does not depend on — so
  installing libei alone still leaves the portal route off and `connect()`
  falls back to the `eis-0` socket that GNOME and KDE do not open. Install
  `liboeffis` to get the fast path.

### A Monitor Left of the Primary Broke Every Wayland Capture Path

- **Wayland has no per-monitor screen, and the one it does have need not start
  at `(0, 0)`.** The compositor lays every output out on a single plane, and
  that plane starts at a negative coordinate the moment an output sits left of
  or above the origin — which is what "my second monitor is on the left" means
  to a compositor. sway's headless backend accepts `output HEADLESS-1 position
  -1280 0`, so this is now a layout CI can stand up: two 1280x720 outputs, one
  2560x720 capture, top-left pixel at x=-1280.
- **`screen.size()` was returning the layout's right edge, not its width.** It
  computed `max(x + width)` over the outputs, which is 1280 on that layout
  while `grab_image()` returns a frame 2560 wide. Everything that composes the
  two believed the smaller number: the mss-shaped shim's monitor list (and so
  `enumerate_monitors`), the screen recorder, the WebRTC host and the MCP
  monitor grab all asked for a rectangle half the size of the desktop and
  reported it as the whole screen.
- **The crop for the tiers that cannot take a region cropped in the wrong
  space.** Only grim accepts a geometry; gnome-screenshot, spectacle, the
  portal and `JE_AUTOCONTROL_WAYLAND_CAPTURE_COMMAND` all hand back the whole
  layout and AutoControl crops afterwards. That crop used layout coordinates
  against an image whose origin is the layout origin, so asking for
  `[-1275, 5, -1175, 55]` — a rectangle on the left-hand monitor — asked
  Pillow for a box 1275 px left of the frame and got black padding.
- **And a match found on that monitor was reported on the wrong one.**
  `grab_logical`, the capture behind template search, OCR and visual match,
  reads its origin from `GetSystemMetrics`, which says nothing off Windows —
  so it returned `(0, 0)` and every hit came back 1280 px to the right of
  where it was seen. That reads as "the click lands on the wrong screen"
  rather than as a failure to find, which is the worse of the two.
- **Fixed at the seam, not at the call sites.** The Wayland backend publishes
  `layout_origin()`; `size()` returns the bounding box's *size*; `grab_image`
  subtracts the origin before cropping; and
  `screen_grabber.backend_layout_origin()` is what `grab_logical` and the mss
  shim ask, so a backend that captures its own screen can say where that
  capture starts. Backends the generic libraries can already see (Windows,
  macOS, X11) publish nothing and are unchanged — the origin is only ever
  asked for, never guessed.
- **Verified against a real compositor, both ways round.** The
  `wayland-verification` job now runs its 27 checks twice: once with the
  outputs side by side from the origin, once with the left-hand one at
  x=-1280. The second run is what pins the negative case end to end — grim's
  negative `-g`, the reported size, `layout_origin()`, the mss shim's monitor
  rectangle, `grab_logical`'s origin, and the fallback crop driven through the
  operator override pointed at grim so a *real* whole-layout PNG goes through
  the code path that has to shift it.

### The Same Layout Problem, on the Input Side — a Move libei Was Dropping in Silence

- **libei discards an absolute motion that lands in no region, and reports
  nothing about it.** No return code, no event, no error the caller can see —
  `ei_device_pointer_motion_absolute` simply does not put the event on the
  wire. `set_position` then returned as though the pointer had moved. Measured
  against a real EIS peer, not inferred: with the device offering one
  `(0, 0, 1920, 1080)` region, `(1919, 1079)` arrives and `(1920, 1080)`
  produces no server-side event at all.
- **And the space those regions live in need not be the layout's.** A region's
  offset is a `uint32`, so no compositor *can* advertise one left of or above
  the origin — while this project's layout space starts at `layout_origin()`
  and goes negative the moment a monitor sits left of the primary. That is the
  exact desktop the capture half was just fixed for. The two halves therefore
  disagreed by the origin, which is the case where `get_pixel(x, y)` and
  `set_position(x, y)` name different pixels — and the pointer that would have
  gone to the wrong monitor instead went nowhere, quietly.
- **`LibeiBackend` now reads the device's regions and maps the point into
  them.** `ei_device_get_region` and the four `ei_region_get_*` getters are
  bound; `_region_point` sends a covered coordinate unchanged, retries an
  uncovered one normalised by the layout origin, and refuses what neither
  covers. A device that declared no region accepts anything and is passed
  through untouched, which is measured too — that is the common single-monitor
  case, and it costs nothing.
- **A refusal is the useful outcome, not a failure.** It is a
  `LibeiUnavailable`, so `_select_input.emitted` hands the move to the ydotool
  path exactly as it already does for a paused device. libei is documented as
  the fast path and never the only one; the bug was that a dropped move never
  reached the fallback because nothing knew it had been dropped. The frame is
  not sent on a refusal either — nothing was buffered, and a frame there would
  commit whatever the previous emission left on the device.
- **The layout origin is only consulted when a point misses.** It costs a
  `wlr-randr` subprocess, so it stays off the path every ordinary mouse move
  takes, and it answers `(0, 0)` on GNOME and KDE — which is the right answer
  there rather than a fallback, because those compositors normalise the layout
  themselves.
- **Five new checks in the `eis-verification` job, against the real
  protocol.** That the client reads back the offsets the compositor
  advertised; that a region at `x=1280` takes `1380` for a point 100 px into
  it rather than `100`; that libei still drops an out-of-region motion without
  a word — the measurement the whole guard rests on, so a future libei that
  clamps instead says so; that AutoControl refuses such a move rather than
  losing it; and that `(-1280, 10)` on a layout starting at `-1280` reaches
  the server as `(0, 10)`. The job now runs 20 checks.
- **What this does not settle.** ydotool's `mousemove --absolute` has an
  origin of its own — it clamps to the compositor's top-left corner and sends
  the target as a relative delta — and whether that corner is the layout
  origin needs a compositor that consumes libinput devices. That is what the
  `seat-verification` job later built, and it answered this: the origin is
  the layout's top-left corner, not the layout coordinate `(0, 0)`.

### The ydotool Path Was Reporting Success While Doing Nothing

- **`apt install ydotool` — the hint this backend printed — installs a
  version whose command line cannot run it, and which says so by exiting
  zero.** ydotool 1.0 replaced the whole CLI, and every argument the Wayland
  backend builds arrived in that release: `mousemove --absolute`, `mousemove
  --wheel`, hex `click` bitmasks (which is what lets a press and a release be
  sent separately, and therefore what makes drag possible), and `key
  CODE:STATE` taking numeric evdev codes. Debian bookworm, Ubuntu 22.04 and
  Ubuntu 24.04 all still ship 0.1.8 under that name. Measured against a real
  uinput device, 0.1.8 answers `click 0x40` with **no events and exit code
  0**, and answers `mousemove --absolute` with `unrecognised option` — also
  **exit code 0**. The backend runs ydotool with `check=True`, so a non-zero
  status was the only thing that would have raised. On those distributions a
  script clicked nothing, typed nothing and moved nothing, and every call
  reported success.
- **The legacy CLI is now refused before anything is sent.**
  `linux_wayland/_ydotool_cli.py` classifies the installed ydotool once per
  process — mouse and key dispatch cannot afford a subprocess per event — and
  raises with the three routes out: a 1.0+ package, a source build, or
  `JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11`. Neither series implements
  `--version` and 1.x will not answer `--help` without its daemon running, so
  the probe reads the one thing both print with no daemon and no side
  effects: the no-argument command list. A version it does not recognise is
  allowed through rather than blocked, so a future release that changes that
  banner cannot be locked out by a stale detector.
- **Both install hints were wrong in a second way.** Debian trixie ships no
  `ydotool` package at all. The hints now name the distributions that do.

### ydotool Never Needed a Desktop to Verify — Only a Reader

- **The gap both verification images recorded turned out to be the wrong
  gap.** `Dockerfile.wayland` and `Dockerfile.eis` each closed by saying
  ydotool "needs /dev/uinput and a seat that consumes it", and `Progress.md`
  filed that behind building a GNOME VM. A seat is what makes an injected
  event *arrive somewhere*. It is not what makes one *observable*: ydotoold
  creates an ordinary uinput device, the kernel publishes it as
  `/dev/input/eventN`, and reading that node returns the exact `input_event`
  structs ydotool wrote. No compositor, no session, no VM.
- **`docker/Dockerfile.ydotool` and `docker/ydotool_verify.py` do that, in
  CI, in twelve checks.** They settle what had only ever been asserted
  against mocks: `0xc0` / `0xc1` / `0xc2` really are BTN_LEFT / BTN_RIGHT /
  BTN_MIDDLE; the split edges `0x40` and `0x80` really do send a press with
  no release and a release with no press, which is the entire basis of
  `press_mouse` and drag; `key 30:1 30:0` really does carry numeric evdev
  codes; and **the wheel signs are measured rather than assumed** — `-y 1`
  reaches the kernel as `REL_WHEEL +1`, `-y -1` as `-1`, and `-x 2` as
  `REL_HWHEEL +2` with the axes not swapped. That last one is the assumption
  `Progress.md` had flagged as untested since the scroll work landed.
- **The twelfth check drives the backend's own functions rather than a
  hand-written argv**, so "what ydotool does with this command line" and
  "what AutoControl sends" are joined rather than merely adjacent.
- **`mousemove --absolute` does not emit absolute events**, which is worth
  knowing before trusting it. ydotool 1.x has no ABS axes on its device: it
  sends `INT32_MIN` on both relative axes first, relies on the compositor
  clamping that to the top-left corner, and then sends the target as a
  relative delta. So `set_position` lands on the requested pixel *because of
  that clamp*. The kernel side is now pinned; the clamp is the compositor's
  behaviour and stays open.
- **The container gets `/dev/uinput` and character major 13, not
  `--privileged`.** ydotoold creates its input node *after* the container
  starts, which `--device` cannot cover, so the job grants
  `--device-cgroup-rule 'c 13:* rmw'` and nothing else.

### Scrolling on Wayland Stops Needing a uinput Daemon

Motion, buttons and keys had already moved onto libei. Scroll was the one
input left shelling out to `ydotool` for every notch, and `Progress.md` said
why: the sign was a guess, and a scroll that goes the wrong way fails
silently. It is wired now, and the guess has been replaced with two
independent readings plus a measurement.

- **The two paths count wheel detents in opposite directions.** This
  repository's `wayland_scroll_direction_*` constants are in the kernel's
  `REL_WHEEL` frame, because that is what ydotool writes into `/dev/uinput`:
  positive is up. libei is in the `wl_pointer` / libinput frame, where
  positive is down — libinput's own evdev reader negates `REL_WHEEL` to get
  there, and the other libei sender that documents its sign (enigo) passes a
  "positive scrolls down" value straight through to `scroll_discrete`.
  Horizontal needs no flip: `REL_HWHEEL` and libinput both count right as
  positive. So the vertical axis is negated on the way to libei and the
  horizontal one is not, which is the decision `Progress.md` was waiting on.
- **The flip is checked against the real EIS server, negative value and
  all.** A fifteenth check in `docker/eis_verify.py` drives the *public*
  `mouse.scroll()` — not the backend method the earlier check drives — and
  reads back `(0, -120)` for up, `(0, 120)` for down and `(120, 0)` for
  right. It is also the only place a negative discrete value reaches the
  wire; the earlier check only ever sent a positive one, so a marshalling
  fault on the sign had nowhere to show up.
- **A refused emission now falls back to the CLI, which is what the code
  always claimed.** `libei`'s module docstring says every failure raises
  `LibeiUnavailable`, "which `keyboard` / `mouse` already treat as *use the
  ydotool CLI*". Only the *connection* was treated that way. Once a backend
  was handed over, a compositor that paused a device — or a session that
  ended between two calls — raised straight out of `set_position`,
  `press_key` or `hotkey`. Routing scroll through libei would have added a
  fourth way for a script to die on a path that has a working fallback
  sitting next to it, so the fallback was made real: a chord refused
  part-way releases what it already pressed before handing over, so no
  modifier is left held, and a button whose *release* is refused is released
  by ydotool rather than staying down for the rest of the session.
- **`LibeiUnavailable` was escaping every containment boundary.** It
  inherited `RuntimeError` alone, and `CLAUDE.md` is explicit that a
  framework error which is not an `AutoControlException` "silently escapes
  every boundary" — the executor, the background poll loops, the request
  handlers, the GUI slots. It now inherits both, so the probes that catch
  `RuntimeError` keep working and the boundaries finally see it.

## What's new (2026-08-18)

### The libei Input Path Now Has Something to Talk To

The Wayland capture path was verified against a real compositor; the *input*
path was not, and was recorded as needing a GNOME VM. It does not. libeis is
the server side of libei's own protocol, Debian packages it, and the two
libraries will talk to each other over a plain Unix socket — so
`docker/eis_server.py` runs a real EIS implementation and
`docker/eis_verify.py` drives AutoControl's real sender against it. No
compositor, no desktop session, 14 checks, wired into CI.

- **Discrete scroll was off by a factor of 120.** libei measures discrete
  scroll in 120ths of a wheel click — the same convention as Windows'
  `WHEEL_DELTA` — and `scroll()` was passing raw detent counts, so one click
  asked for 1/120th of a scroll. libei says so at runtime ("suspicious
  discrete event value 1, did you mean 120?"), which no mock was ever going to
  print. `scroll(0, 1)` now arrives at the server as `(0, 120)`: one click,
  right axis, right sign. This was the path `Progress.md` left deliberately
  unwired because the *sign* was a guess; the sign turned out to be the
  smaller half of the question.
- **The teardown no longer leaks a context per process.** `ei_unref`
  segfaults on libei 1.3.901 — but only on a context whose backend opened and
  whose handshake never progressed. With a peer to complete a handshake
  against, the live case is finally testable, and it is safe. Teardown now
  releases the devices and the context normally and abandons only the state
  that actually crashes, instead of abandoning every opened backend on the
  suspicion that it might.
- **The values a mock cannot check are checked.** The server offers six
  capabilities and reads back what the client actually bound: exactly the four
  AutoControl asks for, so both the `EI_DEVICE_CAP_*` bitmask and the variadic
  `ei_seat_bind_capabilities` marshalling are right. Key codes, absolute
  coordinates and button codes are read off the wire and compared. Every
  emission is confirmed to carry a frame, and every device to open an
  emulation transaction first — libei drops events from one that has not.
- **Two things measured but not ours to fix**, recorded rather than papered
  over: `eis_device_pause()` puts nothing on the wire for a sender client on
  libeis 1.3.901, so the client's `DEVICE_PAUSED` handling still has no peer
  to exercise it; and the `start_emulating` sequence number does not survive
  the trip (an explicit 4242 reads back as 0), so AutoControl's counter cannot
  be checked from the far side. The check is written so that a libeis which
  starts sending pauses will fail loudly if the client ignores them.

### The Architecture Map's Line Counts Are Measured Again

- **The map quoted the same subsystem at two different sizes.** `CLAUDE.md`
  says every figure in `architecture_explore.md` is measured, but nothing
  checked it, and two counting conventions had grown up side by side: the §5.4
  theme tables and the §5.4.17 file tables counted a phantom trailing line —
  `len(text.split("\n"))` reports one line more than a file that ends in a
  newline actually has, and one more *per file* for a package — while §1's
  totals and the §8 appendix counted correctly. So `utils/executor/` was 8,811
  lines in one section and 9,001 in another, and the §8 column did not add up
  to its own total. On top of that about fifty rows were simply stale, several
  `####` headings were hundreds of lines out (`linux_wayland/` was still
  quoted at 10 files / 1,093 lines against a real 14 / 2,235), and one theme
  table had gained two subpackages its summary line never heard about.
- **413 figures re-measured** on one convention — `len(text.splitlines())`,
  what `wc -l` reports and what `CLAUDE.md`'s own over-750-lines snippet
  counts. §5.4, §5.4.17 and §8 now agree with each other for every subsystem,
  and §8's rows sum to its stated total.
- **`test_doc_line_counts.py` is both the gate and the fix.** It fails CI when
  any quoted line count stops matching the tree, naming the offending lines,
  and rewrites all of them in place with `--fix`. The line counts were the one
  part of the map with no gate — the command, MCP-tool, subpackage and example
  counts already had `test_doc_counts.py` — which is exactly why they were the
  part that drifted.

### The Clipboard No Longer Fails Because Another Application Was Copying

- **One process at a time may hold the Windows clipboard open, and every
  clipboard call in AutoControl gave up the instant one did.** Explorer,
  Office and every browser own the clipboard for a few milliseconds at a time
  while they copy; `OpenClipboard` returns false for that whole window and all
  six call sites — text, image, HTML, RTF, CSV, file drops, format
  enumeration — turned it straight into `RuntimeError: OpenClipboard failed`.
  Measured on a live desktop with a second process copying in a loop: about
  one open in a thousand failed, which is a script that dies for no reason the
  operator can see or reproduce. Win32 documents this as the condition to
  retry, and a library whose job is driving a machine that other applications
  are busy on cannot treat "somebody else was copying" as an error.
- **`win32_clipboard_api.open_clipboard()` is now the single place that opens
  it**, waiting out a busy clipboard for roughly 200 ms before reporting
  failure, and closing it however the block ends. The three modules that
  hand-rolled the open/close pair — including the two that predated the shared
  module — go through it, so the retry cannot be forgotten at a new call site.
- **The clipboard round-trip tests no longer depend on what the rest of the
  machine is doing.** They exercise the real Win32 calls, which is the only
  place the four historical writer bugs could ever be seen, so faking the
  backend would have deleted the coverage instead of stabilising it. They now
  read the Win32 clipboard sequence number instead: unchanged between the
  write and the read means nothing else wrote in that window, so the assertion
  is about AutoControl's code and nothing else. Verified against a process
  making 4,112 competing clipboard writes during the run.

### A Misspelled Command Name Is a 400, Not a 500

- **`POST /execute` answered `500 {"error": "execute_action failed"}` for an
  `AC_*` name that does not exist**, which is the same answer it gives when
  the server itself breaks. A client could not tell a typo in its own request
  from an outage, and the message did not say which name was unrecognised.
- **Every command name is now checked before anything runs**, and an
  unrecognised one comes back as `400` listing *all* of them in
  `unknown_commands` — nested flow-control bodies included — so a client fixes
  every typo in one round trip. `POST /execute_file` answers the same way for
  a file that is unreadable, is not an action list, or names an unknown
  command. The OpenAPI spec documents both, and states that a rejected request
  executed nothing.
- Validation and collection share one traversal in `action_schema`, so there
  is still exactly one definition of where a nested action list may hide.

### A Segfault in the libei Teardown, and the Binding Checked Against the Real Library

- **`ei_unref` crashes the process on libei 1.3.901 once a backend is open,
  and the fallback path ran straight into it.** Every failure mode of the
  libei handshake ends in `_teardown()`, so on any host where libei is
  installed and the handshake does not complete, AutoControl died with
  SIGSEGV instead of quietly using ydotool — the exact opposite of the
  fail-closed promise. Measured one call at a time against the real library:
  `ei_unref` is safe with no backend set up and safe after a *failed* setup,
  and segfaults after a successful one. `ei_disconnect` crashes in the same
  state, so it is not a refcounting mistake here; the header documents
  `ei_unref` as correct for both outcomes, which makes this an upstream bug.
  An opened backend is now abandoned rather than unreffed — a bounded leak of
  one context per process, against a crash in a library that drives a desktop.
  A sentinel in the verification re-checks the upstream state on every run and
  says so when the workaround can go.
- **Every entry point the binding names is now resolved against the real
  `libei.so`.** A misspelled symbol or a wrong `argtypes` sails past a mocked
  symbol table and only surfaces on a user's machine; all 22 prototypes plus
  the variadic `ei_seat_bind_capabilities` are checked for real.
- **The whole fail-closed chain runs end to end**: connect to a socket that
  speaks no EI → handshake times out → `LibeiUnavailable` → `active_backend()`
  returns None → `press_key` falls through to the ydotool CLI.
- **`liboeffis` is not packaged everywhere.** Arch and Fedora ship it; Debian
  trixie does not. Without it there is no portal route, so `connect()` falls
  back to the well-known EIS socket — which GNOME and KDE do not create. The
  libei fast path is therefore unavailable on those systems, and says so
  rather than looking mysteriously idle.

### The Wayland Capture Path Now Meets a Real Compositor

- **`screen.size()` reported one monitor while `grab_image()` returned the
  whole layout.** The `wlr-randr` parser took the first `WxH` anywhere in the
  document, which is the first output's current mode. On a two-monitor layout
  that is half the screen — and the two are composed by the mss-shaped shim,
  so the recorder, WebRTC and MCP monitor paths asked for a region half the
  size of the screen and got it. `size()` is now the layout bounding box, from
  a parser that reads every enabled output's mode *and* position. Found by
  running against a real compositor; no mock had a second monitor.
- **`docker/Dockerfile.wayland` runs the backend under headless sway.** The
  wlroots headless backend needs no GPU, no seat and no display, so a genuine
  Wayland session fits in a container — and now in CI, as the
  `wayland-verification` job. Two outputs are painted different solid colours,
  because on a uniform screen a region grab cannot be caught reading the wrong
  rectangle, and a red/blue swap cannot be caught at all.
- **21 checks that were previously mock-only now run against pixels the
  compositor painted**: grim's argv and `-g` geometry, RGB channel order,
  `wlr-randr`'s undocumented output format, `size()` / `grab_image()` /
  `get_pixel()` / `screenshot()`, `je_auto_control.screenshot()`'s BGR output,
  `grab_logical()` (the locator and OCR path), the mss shim, and `wtype`.
- **What the container cannot answer is stated rather than glossed over.**
  ydotool needs `/dev/uinput` and headless sway consumes no libinput devices;
  `xdg-desktop-portal-wlr` implements no RemoteDesktop, so there is no
  `ConnectToEIS` to test. Both remain open in `Progress.md`.

### libei Input, End to End

- **The full portal handshake is implemented.** libei is not a
  call-a-function-and-a-key-is-pressed library: a sender has to open an EIS
  backend, bind a seat's capabilities, take a device *out of an event*, start
  emulating on it, and follow every emission with `ei_device_frame` or nothing
  is delivered. All of that now happens, so `press_key`, `set_position` and the
  mouse buttons can emit without spawning a process per event.
- **The EIS socket comes from the desktop portal.** On GNOME and KDE it is not
  a path on disk — it is a file descriptor handed over D-Bus by
  `org.freedesktop.portal.RemoteDesktop.ConnectToEIS`, after a three-call
  asynchronous session dance. No command-line tool can pass a file descriptor
  into this process, so the `gdbus` route used for screenshots cannot work
  here; `liboeffis` (which ships with libei for exactly this) does the dance.
  Where liboeffis is absent, the well-known `$XDG_RUNTIME_DIR/eis-0` socket is
  still tried.
- **Devices come from events, never from the context.** The previous binding
  passed the `struct ei *` context to entry points that take a
  `struct ei_device *` — pointer type confusion in a C library. That is now
  impossible by construction.
- **A failed probe is paid once, not per keystroke.** The handshake involves a
  portal round trip and possibly a consent dialog. The result is cached for the
  process, so a host where libei is installed but unusable does not re-attempt
  it on every key press.
- **Everything still falls back to ydotool.** Missing library, declined
  consent, a partial capability grant, a paused device, a handshake that does
  not complete — each raises `LibeiUnavailable`, which the keyboard and mouse
  modules already treat as "use the CLI". Scroll deliberately stays on ydotool:
  its direction convention is pinned by tests, and a wrong sign would fail
  silently rather than loudly.
- **The ABI constants were checked against the upstream headers**, not
  guessed. Three were wrong. `enum ei_device_capability` is a *bitmask*, so
  `EI_DEVICE_CAP_KEYBOARD` is `1 << 2`, not 3; `OEFFIS_EVENT_CLOSED` comes
  *before* `OEFFIS_EVENT_DISCONNECTED`; and `OEFFIS_DEVICE_ALL_DEVICES` is a
  `= 0` sentinel rather than the OR of the device bits. The capability error
  was the expensive one — no device would ever have reported the capability,
  so every session would have timed out and silently used the CLI. The
  verified values are now pinned by tests. The session also asks only for the
  keyboard and pointer it actually drives, so the consent dialog does not
  request a touchscreen grant nothing uses.

### Wayland Capture Has a Floor Under It

- **`xdg-desktop-portal` backs up the three CLI helpers.** None of `grim`,
  `gnome-screenshot` or `spectacle` is guaranteed to be installed — GNOME has
  not shipped `gnome-screenshot` by default since 42 — so
  `org.freedesktop.portal.Screenshot` is tried last through `gdbus` rather than
  giving up. It is awkward by nature: the portal returns a request handle and
  answers later with a signal, so the listener starts before the call is made,
  and the wait is bounded (30s) because a consent dialog can sit in front of it.
- **An operator can name their own capture command.**
  `JE_AUTOCONTROL_WAYLAND_CAPTURE_COMMAND="mycap --png {output}"` wins over
  every detected tool. `{output}` becomes a temporary PNG path, substituted per
  argument after `shlex.split` and run without a shell, so a path with spaces
  stays one argument. This is the escape hatch for a setup none of the built-in
  tiers fit — including one where our argv guess for a helper turns out wrong.
- **libei refuses a connection it cannot emit through.** The binding only ever
  holds an `ei` context, while every device entry point takes an `ei_device`,
  and it runs none of libei's seat / device / `start_emulating` / `frame`
  handshake — so it could not deliver input, but *could* pass the wrong pointer
  into a C library on a host that opens `$XDG_RUNTIME_DIR/eis-0`. It now stops
  at `connect()` with an explanation. Callers already treated that as "use the
  ydotool CLI", which is what every real desktop was doing anyway.
- **The portal listener cannot wedge on shutdown.** Its pipe is closed only
  after the reader thread lets go of it; closing a stream out from under a
  blocked `read()` can hang on the buffer lock, which would have turned a
  timed-out capture into the hang the timeout exists to prevent.

### The Container Image Builds and Starts From a Windows Checkout

- **Every container built on a Windows clone died on startup.** `.gitattributes`
  said `* text=auto`, so `docker/entrypoint.sh` and `docker/entrypoint-xfce.sh`
  were checked out with CRLF. The shebang then reads `#!/bin/sh<CR>`, the kernel
  looks for an interpreter whose name ends in a carriage return, and the image
  builds perfectly and then exits with `exec /usr/local/bin/autocontrol-entrypoint:
  no such file or directory` — a message that names the file it just failed to
  find. CI never saw it: a Linux runner checks the same file out with LF.
  `*.sh text eol=lf` now pins it, and a test asserts no entrypoint carries CRLF.
- **`.dockerignore` was in `docker/`, where Docker does not look.** Docker reads
  it from the build *context* root, and every documented build passes the
  repository root (`docker build -f docker/Dockerfile .`), so the exclusions did
  nothing: `.git`, `.venv`, `test/` and the caches were all being shipped to the
  daemon on every build. Moved to the root, where it takes effect.
- **The `mss` shim test measured the host's monitor, not its own fake.**
  `test_screen_grabber.py` patched `backend_grab_image` but left
  `_backend_screen_size` reading the real `platform_wrapper.screen`, so
  `monitors[0]` reported whatever display the developer had. It passed on a
  1920x1080 desktop and failed under a 1280x800 Xvfb, for reasons unrelated to
  the code under test. The fake now owns both halves of the seam.

## What's new (2026-08-17)

### Wayland Sees the Screen

- **Every capture path now goes through the platform backend.** `screenshot()`,
  the image and anchor locators, OCR, smart waits, visual regression, screen
  recording, the MCP monitor tools and remote desktop each reached for
  `PIL.ImageGrab` or `mss` directly. Both read the X11 root window on Linux,
  which under Wayland belongs to XWayland and does not composite native Wayland
  windows. Pillow does fall back to `gnome-screenshot` / `grim` / `spectacle`,
  but only inside `except OSError` around its X11 grab — so it fires when there
  is no X display at all, and *not* while XWayland is up, which is the default
  on GNOME, KDE and sway. `mss` has no fallback in any configuration.
  `utils/cv2_utils/screen_grabber.py` is now the one place that decides how
  pixels are read: a backend that publishes `grab_image` gets wrapped in
  whichever library shape the caller already uses. Windows, macOS and Linux X11
  publish nothing and keep the real libraries, so their behaviour is
  byte-for-byte unchanged.
- **Wayland capture covers three compositor families, not one.** `grim` only
  speaks `wlr-screencopy`, which GNOME and KDE do not implement — so
  `linux_wayland/capture.py` tries `grim` (sway, Hyprland, river), then
  `gnome-screenshot`, then `spectacle`, and reports which one it used. Only
  `grim` can take a region itself; the others capture the screen and the region
  is cropped from it.
- **A missing capture tool fails loudly.** It raises with the install command
  for each compositor rather than handing back an empty XWayland grab that
  reads downstream as "template not found". The new `screen_capture`
  diagnostics check names the tool in use before anything has to fail.
- **`screen.size()` and `get_pixel` work off GNOME/KDE too.** Resolution falls
  back from `wlr-randr` to measuring a capture, and `get_pixel` crops a 1x1
  region from whichever capture path is available.

### Which Program Owns That Window

- **`foreground_window_process_id` / `window_process_id`** (`AC_foreground_window_pid`,
  `AC_window_pid`, `ac_foreground_window_pid`, `ac_window_pid`, two Script Builder
  specs; Windows backend `get_window_process_id`): a window title is whatever the
  application decides to display, and unrelated programs share titles like
  `Settings`, so "which program is the user in front of" had no reliable answer.
  It does now, and callers can join it against a process list. Unavailable reads
  as `None` — never a bare `0`, which would match the System Idle Process.
- **The two older window-input functions are deprecated and now work.**
  `send_key_event_to_window` / `send_mouse_event_to_window` posted to the frame,
  which reaches nothing in a window with child controls; they delegate to the
  new pair, warn once, and keep their old argument types working.
- **`get_pixel` no longer risks a truncated device context.** The Windows screen
  backend declared no prototypes, so an HDC — pointer-width — came back through
  ctypes' default `c_int`, and the same truncated value was passed on to
  `GetPixel` and `ReleaseDC`. Every prototype is declared and the module owns
  private DLL handles, so the declarations cannot leak into other callers.
- **Act on a process's windows, not on a title**
  (`windows_for_process_id`, `minimize_windows_for_process`): a browser names
  its windows after the page they show and runs a dozen processes without any
  window, so "minimise that application" was previously hand-rolled Win32 in
  every caller — enumerate windows, ask each one which process owns it, filter,
  minimise. That loop now lives here once.
- **Typing into a window without stealing focus actually works now**
  (`post_key_to_window`, `post_click_to_window`, `AC_post_key_to_window`,
  `AC_post_click_to_window`, `ac_post_key_to_window`, `ac_post_click_to_window`).
  The existing `send_key_event_to_window` posted to the top-level frame, and
  keyboard messages go to the control that *has focus* — so it silently did
  nothing in any application with child controls while still reporting success.
  Measured on Character Map: posting to the frame typed nothing, posting to the
  focused edit typed the character; on Windows 11 Notepad the new path types
  into a background window while the foreground window keeps focus. Clicks
  resolve the deepest child under the point and convert to its client
  coordinates. This is still best effort by nature — games and anything reading
  raw input ignore posted messages — so both functions return whether the
  messages were queued rather than claiming the application acted.
- **Half the clipboard was broken on 64-bit Windows, and nothing noticed.**
  `set_clipboard_files`, `set_clipboard_html`, `set_clipboard_rtf` and
  `set_clipboard_csv` raised `OverflowError` on every call — four writers that
  had never once worked. Each module declared `restype` but not `argtypes`, so
  a pointer-width memory handle went through ctypes' default `c_int`. The
  pure-function tests could not see it (the byte packing was always right) and
  nothing exercised the Win32 half. The prototypes now live once in
  `utils/clipboard/win32_clipboard_api.py`, every clipboard module goes through
  it, and a new test round-trips text, HTML, RTF, CSV and file lists through the
  real clipboard — plus a static check that no module hand-rolls those calls
  without declaring prototypes again.
- **`save_window_layout` no longer records windows it cannot restore.** Its
  docstring promised titled windows; the default lister returned all of them,
  while `restore_window_layout` addresses a window by title and skips blank ones.
  On a real desktop that was 28 entries saved against 15 restorable — a caller
  reporting the saved count was over-promising by a factor of two. The lister now
  passes `titled_only=True`, and a round-trip test pins save and restore to the
  same set.

## What's new (2026-08-15)

### Text Entry and On-Screen Location That Match What You See

Three defects that made automation miss silently rather than fail loudly: text
that could not be typed, targets that could not be found, and coordinates that
were subtly wrong. All three produced "sometimes it works" behaviour, which is
harder to diagnose than a crash.

- **Type anything, without the clipboard** (`type_unicode_keys`,
  `type_unicode_text`, `AC_type_unicode_keys`, `AC_type_unicode_text`,
  `ac_type_unicode_keys`, `ac_type_unicode_text`): `write` typed through the
  192-entry virtual-key table and *raised* on the first character outside it —
  which on a US layout means `, . / : ? ! _ + @ %` as well as all CJK, so a URL
  or a Chinese sentence failed as a whole string. The Windows backend gains
  `press_unicode` / `release_unicode` / `type_unicode_unit` built on the
  `KEYEVENTF_UNICODE` flag its `KeyboardInput` already understood, and `write`
  now falls back to that route per character instead of raising. The existing
  clipboard-paste `type_unicode` stays, but is no longer the only option: it
  overwrites the user's clipboard and is refused by inputs that block paste, so
  key injection is the default where a backend supports it.
- **Find text the engine split across boxes** (`find_spans`, `group_lines`): OCR
  backends box one *word* at a time, so `Save As` and `另存新檔` had no single
  box to compare against and `find_text_matches` reported nothing for text
  plainly on screen. Matching now scans runs of consecutive boxes on a line —
  grouped by vertical overlap, so it also works for backends that report no line
  ids — and returns the shortest run that spells the target, with the union
  rectangle and the weakest word's confidence. A one-box run is the old
  behaviour, so nothing that matched before stops matching.
- **Capture in the coordinate space the mouse uses** (`grab_logical`,
  `logical_virtual_rect`, `logical_scale`, `needs_rescale`): `find_image` and
  `find_image_multi` captured through `ImageGrab.grab()`, which sees only the
  primary monitor — a target on a second display could never be found. The
  full-desktop capture has the opposite problem: it returns *physical* pixels
  while a DPI-unaware process clicks in *logical* ones, so on a mixed-DPI
  desktop (3840 physical against 3456 logical) a point read off the frame lands
  up to ~116 px away. `monitor_layout.grab_logical` is now the single capture
  primitive behind both OCR and template matching: it covers every monitor,
  rescales into logical pixels, and reports the virtual-desktop origin to add to
  a hit — which is negative whenever a monitor sits left of or above the
  primary. Template matches are translated by that origin, so a located box is
  directly clickable. `find_image` / `find_image_multi` also gained
  `all_screens` and `screen_region`.
- **`visual_match` reports coordinates you can act on.** The scored matcher had
  the same three problems plus one of its own: it captured through
  `pil_screenshot` (primary monitor, physical pixels), and a hit found inside a
  `region` was returned in *region-local* coordinates — so clicking a match was
  wrong by the region's own offset. It now grabs through `grab_logical` and adds
  the origin to every hit; a caller-supplied `haystack` is still its own
  coordinate space, as it must be. Two more traps closed: a template that is
  almost a single colour now raises `AutoControlFlatTemplateException` instead
  of saturating the score map at 1.0 and "finding" the target at an arbitrary
  position, and templates load through `imdecode` so a **non-ASCII path** no
  longer reads as a corrupt file. Everything downstream of `_haystack_gray`
  (`barcode`, `edge_lines`, `edge_match`) inherits the corrected capture.
- **Accessibility search that can actually find the control** (`window_title`
  on `list_accessibility_elements` / `find_accessibility_element`, new
  `find_accessibility_elements`, `contains`, `accessibility_status`,
  `control_get_state`; commands `AC_a11y_find_all` / `AC_control_get_state`,
  MCP `ac_a11y_find_all` / `ac_control_get_state`). Four things stood between
  the API and a real target: the name had to match **exactly**, so a label
  carrying an accelerator (`Save(&S)`) or trailing padding never matched;
  `role="button"` never matched either, because the Windows backend reports the
  raw `ControlType_50000` and nothing translated it; `max_results` truncated the
  list *before* filtering, so an element past the cap could not be found however
  specific the filter; and there was no way to search one window. Scoping is the
  one that matters most for speed — measured on a busy desktop, walking
  everything is 2,085 elements in **61 s** against 135 elements in **0.14 s** for
  a single window. `contains` matching ranks an exact name first, so "OK" offers
  the `OK` button before `OK and close`. `control_get_state` answers what pixels
  cannot — a field's text scrolled out of view, a checkbox's true state, a
  slider's exact number — in one call, with an absent key meaning "no such
  state" rather than "empty"; password fields report only that they are password
  fields, on both `get_value` and `get_state`, because UIA's masking is a
  convention a custom-drawn control can ignore. Elements now also carry
  `enabled`: a disabled control looks clickable and silently swallows the click.
  Conversion cost is gone too — properties come back through one
  `FindAllBuildCache` call instead of one cross-process read per property, and
  the per-element `OpenProcess` for the app name is cached (converting 500
  elements: 0.02 s).

  **A desktop-wide search went from 61 s to about 2 s**, which took three
  separate fixes because there were three separate causes:

  1. *The root.* One `FindAll` from the desktop walks every window's subtree and
     cannot be interrupted. An unscoped listing now takes **one top-level window
     at a time in z-order**, so it can stop as soon as it has enough — and the
     window the user is looking at is searched first.
  2. *The walk.* Even per window, `FindAll` is atomic: one 34,507-element window
     took 10.3 s to answer a request for 200. The walk is now node by node
     through `ControlViewWalker` with a cache request, so asking for 200
     elements costs 200 elements of work (0.036 s for 50, 0.114 s for 200,
     0.486 s for 1,000).
  3. *The provider.* UIA waits on the application itself. A full-screen game
     that never answers made a single `ElementFromHandle` block for **60 s** —
     and it was not detectable in advance: the window pumps messages, replies to
     `WM_GETOBJECT`, and `IsHungAppWindow` says it is fine. The automation object
     now comes from `CUIAutomation8` as `IUIAutomation2` with
     `ConnectionTimeout` bounded, which brings that same call to 1.0 s.

  Measured end to end afterwards: 50 elements 0.20 s, 200 in 1.29 s, 1,000 in
  1.90 s, 3,000 in 3.87 s. Naming a window is still an order of magnitude
  better (0.03 s) and remains the advice.

  `find_*` also separates `max_results` (how many matches to return) from
  `scan_limit` (how many elements to examine) — one number cannot mean both, and
  conflating them turns "up to 40 buttons" into "only look at the first 40
  elements on the desktop".

### Telling You When Your Input Is Going Nowhere

Sent input can be discarded before it reaches anything while the send call still
reports success — the caller is told "clicked (500, 300)", nothing happens, and
no error exists anywhere. `utils/input_reach` (`input_desktop_available`,
`input_reaches_system`, `AC_input_reachable`, `ac_input_reachable`) answers the
question directly.

Two causes needing two checks. A locked workstation is detectable for free by
asking for the input desktop. Input *filtering* is not: measured on a machine
with an anti-cheat game in front, `SendInput` succeeds, `GetAsyncKeyState` never
sees the key, `OpenInputDesktop` reports everything fine, and the game's
integrity level is the same *Medium* as ours — so neither a privilege comparison
nor any cheap query can tell. The only honest test is to send a key and look,
which is why that probe is a diagnostic (it presses F13, which nothing binds)
rather than a gate in front of every action.

### A Recording That Can Actually Be Replayed

`record` captured presses and nothing else, which is not enough to reproduce a
session — and the gap was silent, because the recording looked fine until it was
played back. Three things were missing and one was leaking:

- **Releases.** A press-only log cannot tell a drag from a click, and a modifier
  held across several actions cannot be reconstructed. Verified before the
  change: five press-and-release pairs produced five events.
- **The wheel.** `WM_MOUSEWHEEL` was not handled at all, so scrolling vanished.
  Its `mouseData` high word is a *signed* notch count — read unsigned, a scroll
  down becomes a scroll up by 65,534 notches.
- **Timing.** Without timestamps every step replays at once and no real
  interface keeps up. `utils/input_macro` already had `replay_timeline` waiting
  for `delta_ms` events that nothing produced.
- **A leaked thread per recording.** The listener pumped `GetMessage` once and
  `stop_record` never woke it, so each record cycle left a thread blocked
  forever. Verified: the thread was still alive after `stop_record` returned.

`Win32InputHook` replaces both listeners with one hook that records press *and*
release, wheel deltas and a monotonic timestamp, pumps messages properly, and
exits on `WM_QUIT` when stopped. `stop_record_timeline` (`AC_stop_record_timeline`,
`ac_record_stop_timeline`) returns those events with `delta_ms`, ready for
`replay_timeline`. `stop_record` is untouched and still returns the historical
press-only queue, so existing callers keep working.

New `utils/keyboard_layout` answers the other half: which character a key
produces. Punctuation differs per layout, so a hard-coded US table mislabels
every punctuation key on a German or Nordic keyboard. It asks the **foreground
window's** layout (the user types into what is in front, not into this process)
and only translates **after** recording — `ToUnicodeEx` mutates dead-key
composition state, so calling it mid-typing corrupts the character being
composed.

### One Clipboard Image API Instead of Two

`utils/clipboard` carried two `get_clipboard_image` / `set_clipboard_image`
pairs under identical names — one in `clipboard.py` taking PNG bytes, one in
`clipboard_image.py` taking a file path. Both had live callers, so importing
the wrong module failed at runtime, and only for whichever argument type you
passed. There is one pair now: `set_clipboard_image` accepts **either** PNG
bytes or a path, `clipboard_image.py` is gone, and both functions are exported
from the subpackage and the facade with `AC_clipboard_get_image` /
`AC_clipboard_set_image` commands — previously they were reachable only from
MCP and the GUI, never from `execute_action`.

`windows/listener/` went with it: `Win32KeyboardListener` and
`Win32MouseListener` had no callers left once recording moved to
`win32_input_hook.py`.

### Window Handles You Can Actually Use

Window management listed windows but could not really operate on them.

- **Handles are integers again.** The `EnumWindows` callback declared its hwnd
  as `POINTER(c_int)`, so every handle came back as an `LP_c_long` object;
  `int(hwnd)` on one raises `ValueError`. The list was readable and otherwise
  useless — you could not focus, move or measure anything it returned, and the
  `ac_list_windows` MCP tool raised outright because its handler called
  `int(hwnd)`. Every Win32 prototype in `windows_window_manage` now declares
  `argtypes` / `restype`, which also stops a 64-bit handle being truncated to
  32 bits.
- **`close_window_by_title` closes.** It used to minimise, because Win32's
  `CloseWindow()` minimises despite its name and the wrapper passed that
  through. It now posts `WM_CLOSE` — the same thing the window's own close
  button does, so the application still gets to run its save prompts.
  `minimize_window_by_title` keeps the old behaviour under an honest name.
- **New primitives**: `foreground_window` (what the user is working in),
  `window_rect` (screen rectangle, negative coordinates and all),
  `move_window_by_title` (omit width/height to reposition without resizing) and
  `list_windows(titled_only=True)` — on this desktop that is 17 windows rather
  than 34, the rest being shell and helper surfaces.
- **`focus_window` restores a minimised window** before raising it; focusing a
  minimised window previously did nothing you could see. A maximised window
  stays maximised.

### URL Canonicalisation, Reachable From Every Surface

`utils/url_canon` (RFC 3986 canonicalisation, normalisation and query helpers)
had a working headless core and passing tests, but none of its delivery
surfaces were connected, so it could only be reached by importing the submodule
directly.

- **`canonicalize_url`, `normalize_url`, `urls_equal`, `build_query`,
  `parse_query`** are now re-exported from the facade and listed in `__all__`.
- **`AC_canonicalize_url`, `AC_normalize_url`, `AC_urls_equal`** wire the same
  functions into the executor, so they work from JSON action files, the socket
  server, the scheduler and the Script Builder without Python glue; the
  matching **`ac_canonicalize_url` / `ac_normalize_url` / `ac_urls_equal`** MCP
  tools and three Script Builder `CommandSpec`s come with them.

Comparing two URLs for "the same page" is the actual use: `urls_equal` ignores
query order and the fragment, so `?b=1&a=2` and `?a=2&b=1#top` match, which is
what a navigation assertion needs and what plain string comparison gets wrong.

## What's new (2026-07-18)

### Cross-Platform Reliability Hardening

A full-project runtime audit swept every platform backend and utility for execution-time defects and unexpected behaviour, adding a headless regression test for each fix. There are **no API changes** — existing scripts keep working, they just fail less and behave correctly in more places.

- **macOS (Retina / HiDPI)**: mouse-position reads and omitted-coordinate clicks now land at the correct point. The cursor y-flip used a *pixel*-based display height against a *point*-based cursor, offsetting every implicit click on a 2× display.
- **Remote-desktop relay**: fixed a hang on **Linux + CPython 3.14** where a paired pipe never exited after one peer disconnected — a cross-thread `shutdown()` no longer reliably wakes a blocked `recv()` there, so the pump now polls readability with `select()` and always re-checks its stop flag.
- **USB/IP server** now binds `127.0.0.1` by default (least-privilege); export the device to the LAN with an explicit `host="0.0.0.0"`.
- **Executor**: `AC_expect_poll` no longer crashes on a not-ready value (missing result key or a transiently-failing action) and keeps polling; `AC_parallel` branches are properly variable-scope-isolated, so a nested `AC_execute_action` can't race on the parent's scope; a malformed `run_suite` spec reports a clean error instead of aborting the run.
- **Windows Interception backend**: send-to-window click now performs a real press/release instead of silently no-opping on the button tuple.
- **Wayland**: a partial-coordinate `mouse_scroll` degrades gracefully instead of raising `NotImplementedError`.
- **Typed exceptions preserved at boundaries**: saving an action file with non-encodable text raises `AutoControlJsonActionException` (not a raw `UnicodeEncodeError`); a non-ASCII USB/IP busid no longer kills the client worker thread; SQLite data-source / query connections are always closed; USB ACL rule removal is case-insensitive to match the (case-insensitive) rule matching.
- Builds on the round-3 sweep that reparented the exception family under `AutoControlException` (assertions still propagate under `raise_on_error=False`) and hardened thread-safety across the socket server, scheduler, triggers, and MCP server.

## What's new (2026-07-03)

### Stable API, Failure Bundles, and Release Engineering

A versioned entry point for new integrations, a portable failure-diagnostics format, and a hardened release pipeline. Full reference: [`docs/API_LIFECYCLE.md`](docs/API_LIFECYCLE.md) and [`docs/CAPABILITY_MATRIX.md`](docs/CAPABILITY_MATRIX.md).

- **Stable `je_auto_control.api` façade**: small, lazy, typed namespace (`execute_action`, `execute_action_with_vars`, `generate_code`, `run_diagnostics`, failure bundles) so new consumers can import core automation without eagerly loading hundreds of optional integrations. Governed by a written lifecycle policy — stable removals need a deprecation warning plus two minor releases — with `utils/deprecation.deprecated` supplying consistent, metadata-carrying warnings. CI type-checks this surface with mypy and smoke-imports it on a Windows/Ubuntu/macOS × Python 3.10/3.14 matrix.
- **Failure bundles** (`create_failure_bundle` / `failure_bundle_on_error`, CLI `je_auto_control failure-bundle out.zip`): one atomic, self-contained `autocontrol.failure-bundle/v1` ZIP for diagnosing a failed run — manifest with runtime info, redacted error/context/events, redacted log tail, optional screenshot and diagnostics report, opt-in attachments. Collectors are best-effort: a broken screen grab or diagnostics probe is recorded in `collector_failures` instead of losing the bundle. `codegen --failure-bundle` wraps generated pytest flows so every generated test archives its own failure evidence. Secret redaction now also masks explicit `key=value` / `Authorization: Bearer` credential syntax regardless of entropy.
- **Release engineering**: publishing moves from push-to-main to immutable `v*` tags — the new `release.yml` verifies the tag matches the package version, builds, smoke-tests the wheel, attests build provenance, and publishes via PyPI Trusted Publishing. `quality.yml` gains dependency review, a coverage floor (fail-under 35, branch coverage), and a mypy gate on the stable API; a new platform-smoke workflow exercises the stable API on all three OSes.
- **Project docs**: new [`SECURITY.md`](SECURITY.md) (private-advisory reporting, response targets, operational defaults), [`CHANGELOG.md`](CHANGELOG.md) (Keep-a-Changelog compatibility record), API lifecycle policy, and a capability/platform support matrix. The Sphinx indexes catch up on v182–v223 feature docs in both languages.

## What's new (2026-07-02)

### Menu-Driven GUI: the Actions Menu Replaces In-Tab Buttons

Every tab's commands now live in one predictable place. The window menu bar gains a dynamic **Actions** menu that rebuilds for the active tab; tabs keep only their inputs, tables, and result/status views instead of rows of buttons. Full reference: [`docs/source/Eng/doc/new_features/v223_features_doc.rst`](docs/source/Eng/doc/new_features/v223_features_doc.rst).

- **Window-level Actions menu**: core tabs declare their commands at registration; feature tabs expose a `menu_actions()` hook returning `(label_key, handler)` pairs. 46 of 48 registered tabs now surface their commands this way — Script Builder and Remote Desktop intentionally keep their interactive panel layouts, and the menu shows a placeholder there. Buttons a window-level menu cannot replace stay in place (per-page browse buttons inside stacked trigger forms, the visibility-toggled data-source browse button, stateful auto-refresh checkboxes). A headless regression test guards the contract so no tab can silently lose its commands.

## What's new (2026-06-26)

### Trial and Force Action Modes (Playwright-style)

Dry-run "is this control ready?" without clicking, or force a click past the gate. Full reference: [`docs/source/Eng/doc/new_features/v222_features_doc.rst`](docs/source/Eng/doc/new_features/v222_features_doc.rst).

- **`act_with_mode`** (`AC_act_with_mode`): `actionability.act_when_ready` only waits-then-acts. Real flows need two more modes Playwright codified: **trial** (run every actionability check but *don't* act — a side-effect-free "would this work?" dry run) and **force** (skip the checks and act now — the escape hatch when the gate misjudges a control as occluded/disabled). `act_with_mode` adds both alongside the default `auto`, over the same injectable seams as the gate, returning `{mode, acted, actionable, reason, point, result}`. Reuses `actionability.wait_actionable`; fully testable without a screen. Completes the ROUND-15 input-fidelity lane (7/7). No `PySide6`.

### Act In View — Scroll to a Target, Then Act When Actionable

Click the row three pages down: scroll it into view, then gate on actionability before clicking. Full reference: [`docs/source/Eng/doc/new_features/v221_features_doc.rst`](docs/source/Eng/doc/new_features/v221_features_doc.rst).

- **`act_in_view` / `ScrollPlan`** (`AC_act_in_view`): two reliability primitives stayed separate — `scroll_find.scroll_until_visible` brings an off-screen target on-screen, and `actionability.act_when_ready` waits for it to be visible/stable/enabled/unoccluded before acting. A real "click the off-screen row" step needs both. `act_in_view` composes them: scroll until the target is located, then run the actionability gate at its point and perform the action. `ScrollPlan` bundles the scroll search + its `locator`/`scroller` seams so the call stays within the argument limit; the actionability probes (`region_sampler`/`enabled_probe`/`hit_tester`) and gate `config` are injectable too, so the whole flow is testable without a screen. Closes the input-fidelity lane's composition gap. No `PySide6`.

### Template-Free Element Proposal (Pixels to Elements)

Get a clean numbered element list straight from the screen when there's no accessibility tree. Full reference: [`docs/source/Eng/doc/new_features/v220_features_doc.rst`](docs/source/Eng/doc/new_features/v220_features_doc.rst).

- **`propose_elements` / `tag_kinds`** (`AC_propose_elements`, `AC_tag_kinds`): Set-of-Marks, `observation` and the grounding helpers all assume you already have element boxes — but a game, a custom-drawn app or a remote desktop has no accessibility tree. `propose_elements` builds that top-of-funnel list from pixels: detect widget boxes (closed-edge blobs via Canny + morphology + `connected_boxes`) and text boxes (`text_regions.find_text_regions`), fuse them — the `element_parse` `ocr > icon` priority *is* the "drop widget-that-is-really-text" cross-check — and return them in reading order, each tagged `text` or `widget`. `tag_kinds` is the pure labeller. cv2 imported lazily; the labeller is fully testable. Seventh and final feature of the ROUND-15 perception lane. No `PySide6`.

### Classify a Widget from Its Pixel Shape

Tell a checkbox from a radio button from a text field — from pixels, no model. Full reference: [`docs/source/Eng/doc/new_features/v219_features_doc.rst`](docs/source/Eng/doc/new_features/v219_features_doc.rst).

- **`classify_widget` / `box_features` / `classify_icon`** (`AC_classify_widget`, `AC_classify_icon`): Set-of-Marks and element proposers return *boxes* but not *what each box is*; `form_fields.checkbox_state` reads a box already known to be a checkbox — the gap is the typing step before it. `box_features` extracts `{aspect, fill, edge_density, circularity}` for a box; `classify_widget` is the pure heuristic classifier (round→radio, wide-rounded→toggle, square-sparse→checkbox, wide-hollow→text_field, wide-filled→button, else icon); `classify_icon` composes them. The classifier is pure and fully testable; cv2/numpy imported lazily so the module stays importable. Sixth feature of the ROUND-15 perception lane. No `PySide6`.

### Localize a Change to the Elements That Changed

Turn a raw screen diff into "element 3 changed" by scoring a list of element boxes. Full reference: [`docs/source/Eng/doc/new_features/v218_features_doc.rst`](docs/source/Eng/doc/new_features/v218_features_doc.rst).

- **`localize_changes` / `rank_changes`** (`AC_localize_changes`, `AC_rank_changes`): existing diffs answer *where* pixels changed (`motion_regions`, `perceptual_diff`, `ssim_changed_regions` → raw pixel regions) or which *accessibility* elements differ (`element_diff`, needs metadata) — but not "given a frame diff **and a list of element boxes**, which of *those* changed?". `localize_changes` diffs a reference against the current screen and scores each supplied element box by its mean per-pixel change; `rank_changes` is the pure ranker that flags `changed` (score ≥ `threshold`) and sorts most-changed first. Pairs with `set_of_marks`/accessibility boxes to give a per-element "what changed" feedback signal after a click. cv2/numpy imported lazily; ranking is pure and fully testable. Fifth feature of the ROUND-15 perception lane. No `PySide6`.

### Theme-Invariant Matching (Light Template, Dark Mode)

Find a button captured in light mode even after the app switches to dark mode. Full reference: [`docs/source/Eng/doc/new_features/v217_features_doc.rst`](docs/source/Eng/doc/new_features/v217_features_doc.rst).

- **`normalize_theme` / `match_theme`** (`AC_match_theme`): `match_template` correlates raw pixel intensities, so a light-mode template scores terribly against the same control in dark mode — the polarity is inverted. The fix is to compare *structure*. `normalize_theme` maps an image to a polarity-invariant single channel (`sobel`/`laplacian` gradient magnitude — identical for an image and its colour inverse — or `zscore`); `match_theme` normalizes both the template and the screen, then locates the template via `visual_match.match_template`, finding it across a light/dark flip that defeats raw matching. cv2/numpy are imported lazily so the module stays importable everywhere. Fourth feature of the ROUND-15 perception lane. No `PySide6`.

### Sample a Region's Text Contrast (WCAG)

Grade the legibility of on-screen text when you only have a region, not the two colours. Full reference: [`docs/source/Eng/doc/new_features/v216_features_doc.rst`](docs/source/Eng/doc/new_features/v216_features_doc.rst).

- **`grade_contrast` / `dominant_pair` / `region_contrast`** (`AC_grade_contrast`, `AC_dominant_pair`, `AC_region_contrast`): `a11y_audit.contrast_ratio` grades a foreground/background pair you already know — but a button or label on screen is a *patch of pixels*, not two known colours. `dominant_pair` splits sampled pixels at the mean luminance into the dominant foreground (minority, the text) and background (majority); `grade_contrast` grades a pair against the WCAG 2.x AA/AAA thresholds (normal + large text); `region_contrast` samples a screen region (through an injectable `sampler`) and grades it. The grading and split are pure and reuse `a11y_audit.contrast_ratio`, fully testable without a screen. Third feature of the ROUND-15 perception lane. No `PySide6`.

### Set-of-Marks Label Layout (No Overlap, Readable Colour)

Number every element without the labels piling up or vanishing into the background. Full reference: [`docs/source/Eng/doc/new_features/v215_features_doc.rst`](docs/source/Eng/doc/new_features/v215_features_doc.rst).

- **`place_labels` / `label_color`** (`AC_place_labels`, `AC_label_color`): Set-of-Marks draws each numbered label at a fixed offset, so on dense UIs the numbers pile on top of each other and a dark label on a dark element vanishes. `place_labels` is greedy non-overlap placement — for each mark it tries a ring of candidate positions around its box (above/below/inside, left/right aligned) and takes the first that stays in bounds and clears every already-placed label; `label_color` picks black or white by whichever has the better WCAG contrast against the element background (reusing `a11y_audit.contrast_ratio`). Pure standard library, deterministic, fully testable without rendering. Second feature of the ROUND-15 perception lane. No `PySide6`.

### Colour-Vision-Deficiency Simulation + Collision Check

Check whether your red/green status colours are distinguishable to colour-blind users. Full reference: [`docs/source/Eng/doc/new_features/v214_features_doc.rst`](docs/source/Eng/doc/new_features/v214_features_doc.rst).

- **`simulate_cvd` / `colors_collide` / `color_distance`** (`AC_simulate_cvd`, `AC_colors_collide`): status UIs lean on colour (green "ok" vs red "error"), but for the ~8% of men with a colour-vision deficiency those can be indistinguishable — and nothing in the framework could check it. `simulate_cvd` maps an RGB colour through a dichromat simulation matrix (protanopia/deuteranopia/tritanopia) at a given `severity`; `colors_collide` simulates two colours and reports whether they become confusable (a perceptual `redmean` distance below `threshold`); `color_distance` is the underlying metric. Pure standard library — no numpy/OpenCV, operating on plain RGB tuples, fully testable. First feature of the ROUND-15 perception lane. No `PySide6`.

### Wait Until the App Is Idle

Hold off the next click until the busy/wait cursor settles — don't act mid-churn. Full reference: [`docs/source/Eng/doc/new_features/v213_features_doc.rst`](docs/source/Eng/doc/new_features/v213_features_doc.rst).

- **`wait_until_app_idle` / `idle_point`** (`AC_wait_until_app_idle`, `AC_idle_point`): a click fired while the app is still churning (busy cursor up, dialog mid-paint, long handler running) is dropped or mis-targeted. `smart_waits` watches *pixels* settle; this watches the app's *busy signal* settle, which is cheaper and survives animated-but-idle UI. It reuses `settle_detector.SettleTracker` — each poll feeds 1.0 when busy / 0.0 when idle, and returns once the app has read idle for `quiet_samples` polls in a row (a busy spike resets the run). `wait_until_app_idle` polls an injectable `busy_probe` (default = Windows busy/app-starting cursor) with injectable `clock`/`sleep`; `idle_point` is the pure analyser over a recorded busy/idle trace. Fully testable without an app. Fifth feature of the ROUND-15 input-fidelity lane. No `PySide6`.

### Ensure a Control Is in the Desired State (Idempotent)

Read-compare-act-verify instead of acting blind — don't double-toggle an already-checked box. Full reference: [`docs/source/Eng/doc/new_features/v212_features_doc.rst`](docs/source/Eng/doc/new_features/v212_features_doc.rst).

- **`ensure_state` / `ensure_toggle`** (`AC_ensure_field_value`): automation that acts *unconditionally* double-toggles a box that was already checked or re-enters an already-correct field, and can't be safely re-run. The robust shape is read-compare-act-verify. `ensure_state` reads via an injectable `reader`, and only if it doesn't equal `desired` applies `setter` and re-reads (up to `attempts`); `ensure_toggle` is the boolean specialization that calls `toggle` only while the state differs. A control already in the desired state is left untouched (`changed=False`) — idempotent and safe to re-run, distinct from `idempotency` (a request-key replay cache) since this converges *device state*. The executor's `AC_ensure_field_value` idempotently sets a native control's value via the accessibility backend. Fourth feature of the ROUND-15 input-fidelity lane. No `PySide6`.

### Adaptive Timeout from Observed Durations

Stop guessing wait timeouts — learn them from how long the step actually takes. Full reference: [`docs/source/Eng/doc/new_features/v211_features_doc.rst`](docs/source/Eng/doc/new_features/v211_features_doc.rst).

- **`recommend_timeout` / `timeout_stats`** (`AC_adaptive_timeout`, `AC_timeout_stats`): hard-coded waits are a perennial flakiness source — too short races a slow machine, too long makes every failure pay the full timeout. This learns the timeout from observed step durations: a high percentile (the slow-but-real case) scaled by a safety `factor`, clamped to a sane `[min_s, max_s]` band. `recommend_timeout` is the single number to feed a `wait_for_*` / actionability `GateConfig`; `timeout_stats` also exposes the percentiles and `floored`/`capped` flags for tuning. Both are pure and reuse `stats.percentile`; with no samples they fall back to `default_s`. Third feature of the ROUND-15 input-fidelity lane. No `PySide6`.

### Verify a Field After Typing

Read the field back and confirm the value actually landed — don't type and hope. Full reference: [`docs/source/Eng/doc/new_features/v210_features_doc.rst`](docs/source/Eng/doc/new_features/v210_features_doc.rst).

- **`compare_field_value` / `verify_field_value` / `fill_and_verify`** (`AC_compare_field_value`, `AC_verify_field_value`): `field_entry` types into a control and *hopes* — a slow IME, focus steal, input mask or auto-format can silently mangle or drop characters, and nothing reads the field back. This is distinct from `action_effect` (did *anything* change near the target?) and `postcondition.text_present` (does the text appear *anywhere*?) — neither confirms *this* field equals *this* value. `compare_field_value` is the pure comparator (`exact`/`trim`/`ci`/`normalized` NFKC/`contains`); `verify_field_value` reads through an injectable `reader` (native accessibility value in the executor); `fill_and_verify` types via an injectable `filler`, reads back, and retries (optionally clearing first) until it matches or attempts run out. Every comparison and retry decision is pure and unit-tested without a real control. Second feature of the ROUND-15 input-fidelity lane. No `PySide6`.

### Retry Budget — Deadline + Jitter

Retry a flaky step bounded by a total time budget, with jittered backoff. Full reference: [`docs/source/Eng/doc/new_features/v209_features_doc.rst`](docs/source/Eng/doc/new_features/v209_features_doc.rst).

- **`RetryBudget` / `run_with_budget` / `backoff_delay` / `jittered_delay`** (`AC_retry_delay`, `AC_plan_retry_delays`): `resilience.RetryPolicy` retries a fixed attempt count with plain exponential backoff — it can't express a *wall-clock deadline* ("give up after 30 s total, however many attempts that is") or *jitter* (randomized backoff so retrying workers don't resynchronize into a thundering herd). `RetryBudget` adds both: bounded by `max_attempts` *and/or* `deadline_s`, `run_with_budget` honours whichever is hit first and never sleeps past the deadline; delays use capped exponential backoff with a selectable `full`/`equal`/`none` jitter strategy. The randomness (`uniform`), clock and sleeper are all injectable, so every delay and giveup decision is deterministic in tests. First feature of the ROUND-15 input-fidelity lane. No `PySide6`.

### Live IME State for Safe CJK Entry

Wait for the input method to commit before reading a Japanese/Chinese/Korean field. Full reference: [`docs/source/Eng/doc/new_features/v208_features_doc.rst`](docs/source/Eng/doc/new_features/v208_features_doc.rst).

- **`ime_state` / `is_composing` / `wait_for_composition_commit` / `decode_conversion_mode`** (`AC_ime_state`, `AC_is_composing`, `AC_wait_for_composition_commit`, `AC_decode_conversion_mode`): typing into a CJK field is unsafe while an IME is *composing* — the candidate text isn't committed, so reading the field back returns half-entered glyphs and the next keystroke edits the composition. `text_unicode` (`VK_PACKET`) is blind to this. `ime_state` exposes the focused window's live `{open, composing, composition, conversion}` (Windows IMM32, read-only) through an injectable `reader`; `is_composing` is the boolean gate; `wait_for_composition_commit` blocks until the IME commits (injectable `clock`/`sleep`/`reader`); `decode_conversion_mode` is the pure `IME_CMODE_*` bitmask decoder. All decode/wait logic is unit-tested without an IME. Sixth feature of the ROUND-15 cross-app OS lane. No `PySide6`.

### Lock the Workstation + Wait for Unlock

Lock the box at the end of a run, and block until a human unlocks it before resuming. Full reference: [`docs/source/Eng/doc/new_features/v207_features_doc.rst`](docs/source/Eng/doc/new_features/v207_features_doc.rst).

- **`lock_session` / `plan_lock_session` / `wait_for_unlock` / `wait_for_lock` / `classify_lock_transitions`** (`AC_lock_session`, `AC_plan_lock_session`, `AC_wait_for_unlock`, `AC_classify_lock_transitions`): `session_guard` could *detect* a locked session and raise; this adds *acting* on it. `lock_session` locks the workstation now (`LockWorkStation` on Windows, `loginctl lock-session` / `CGSession -suspend` elsewhere) through an injectable `driver`; `wait_for_unlock` / `wait_for_lock` poll `session_guard.is_session_locked` (reusing its real Windows `OpenInputDesktop` probe) until the state flips or a timeout, with injectable `clock` / `sleep` / `probe`; `plan_lock_session` is the pure per-OS planner and `classify_lock_transitions` reduces a lock-state sample stream to `{event, locked}` lock/unlock events. `wait_for_unlock` is the blocking companion to `ensure_interactive_session`. Fifth feature of the ROUND-15 cross-app OS lane. No `PySide6`.

### Read and Control the System Volume

Set a known audio baseline before a run — mute, set 30%, or assert the level. Full reference: [`docs/source/Eng/doc/new_features/v206_features_doc.rst`](docs/source/Eng/doc/new_features/v206_features_doc.rst).

- **`get_volume` / `set_volume` / `change_volume` / `is_muted` / `set_mute` / `mute` / `unmute` / `toggle_mute`** (`AC_get_volume`, `AC_set_volume`, `AC_change_volume`, `AC_set_mute`, `AC_toggle_mute`): the framework only had the blind media-key steps (`volume up` / `down` nudge by an unknown amount with no read-back). This adds absolute, read-backable control of the default output device — read or set the master level as an integer percent `0..100`, and read / set / toggle the mute flag. All logic (clamping, percent↔scalar conversion, toggle) is pure and runs through an injectable `VolumeDriver` seam, so it is fully unit-tested without an audio device; the default driver uses the Windows Core Audio `IAudioEndpointVolume` interface through the optional `pycaw` dependency (`pip install je_auto_control[audio]`), degrading with a clear error when absent. Fourth feature of the ROUND-15 cross-app OS lane. No `PySide6`.

## What's new (2026-06-25)

### Resolve the App Registered for a File Type

Find out *which* app opens a file type — assert "PDFs open in Acrobat, not the browser". Full reference: [`docs/source/Eng/doc/new_features/v205_features_doc.rst`](docs/source/Eng/doc/new_features/v205_features_doc.rst).

- **`normalize_ext` / `file_association`** (`AC_normalize_ext`, `AC_file_association`): `open_path` (`shell_open`) opens a file with whatever app is registered for it; this answers the inverse, read-only question — *which* app is that? Given `report.pdf` (or a bare `.pdf` / `pdf`) `file_association` returns the registered executable, friendly app name, open command line and MIME content type via the Windows `AssocQueryStringW` shell API. `normalize_ext` is the pure path/`.ext`/bare-`ext` → `.ext` helper. The assembly logic is unit-testable without Windows through an injectable `resolver` seam (the real shell API by default). The natural companion to `open_path`: one tells you what would open a file, the other opens it. Third feature of the ROUND-15 cross-app OS lane. No `PySide6`.

### Idle Detection + Keep the Machine Awake

Run only when the user has stepped away, and stop an overnight run from sleeping. Full reference: [`docs/source/Eng/doc/new_features/v204_features_doc.rst`](docs/source/Eng/doc/new_features/v204_features_doc.rst).

- **`idle_seconds` / `is_idle` / `keep_awake` / `keep_awake_on` / `allow_sleep` / `plan_keep_awake`** (`AC_idle_seconds`, `AC_is_idle`, `AC_plan_keep_awake`, `AC_keep_awake_on`, `AC_allow_sleep`): long unattended runs get derailed two ways — the screensaver / power policy sleeps the box mid-run, or the run should hold while a human is actively using the machine. The framework had neither signal. `idle_seconds` / `is_idle` report time since the last keyboard / mouse input (`GetLastInputInfo` on Windows) through an injectable `probe`; `keep_awake` (scoped context manager) and `keep_awake_on` / `allow_sleep` (process-global on/off for JSON flows) stop the system and display sleeping, applied through an injectable `driver` (`SetThreadExecutionState` / `caffeinate` / `systemd-inhibit` by default) and restored on release. `plan_keep_awake` is the pure planner. All logic is unit-testable without touching the OS via the injected probe/driver. Second feature of the ROUND-15 cross-app OS lane. No `PySide6`.

### Open Files / URLs with the Default App

Hand a file to its default app, print it, or open a URL in the browser. Full reference: [`docs/source/Eng/doc/new_features/v203_features_doc.rst`](docs/source/Eng/doc/new_features/v203_features_doc.rst).

- **`open_path` / `plan_open`** (`AC_open_path`, `AC_plan_open`): the framework could launch a literal `.exe`, but not the most common "hand off to another app" step — open `report.pdf` with its registered app, `print` a document, or open a URL in the default browser. This routes per-OS to `os.startfile` / `open` / `xdg-open` / `webbrowser`. `plan_open` is a pure planner that classifies the target (URL vs file path), validates it (URL scheme allow-list; `realpath` for files — a Windows drive `C:\` is correctly a path, not a scheme) and returns the dispatch descriptor; `open_path` runs it through an injectable `opener` (the real OS call by default), so the logic is unit-testable without launching anything. First feature of the ROUND-15 cross-app OS lane. No `PySide6`.

### Reactive UIA Event Wait (focus change)

Wait until focus lands on the dialog — a real, zero-latency UIA event, not polling. Full reference: [`docs/source/Eng/doc/new_features/v202_features_doc.rst`](docs/source/Eng/doc/new_features/v202_features_doc.rst).

- **`wait_for_focus_change`** (`AC_wait_for_focus_change`): the accessibility recorder *polls* focus every ~250 ms, so it can miss a fast transition and reacts late. This blocks on the native `AddFocusChangedEventHandler` and returns the moment focus moves — the zero-latency, miss-free "wait until focus lands on the dialog" primitive, the accessibility-tree analogue of `wait_for_window` / `wait_for_image`. Returns the newly-focused element (or `None` on timeout). The real event subscription is registered/unregistered under a lock on the calling thread; dispatched through the injectable accessibility backend seam (headless-testable via a fake backend; real UIA in the Windows backend). No `PySide6`.

### Container Selection + View Switching (Selection / MultipleView)

Read what's selected in a listbox/grid, and switch Explorer-style views. Full reference: [`docs/source/Eng/doc/new_features/v201_features_doc.rst`](docs/source/Eng/doc/new_features/v201_features_doc.rst).

- **`get_selection` / `list_views` / `set_view`** (`AC_get_selection`, `AC_list_views`, `AC_set_view`): `select_control_item` selects *one* item, but the container-level `SelectionPattern` answers "what is currently selected, and may it select multiple?" — the assertion target after selecting. `MultipleViewPattern` switches a control between its views (Explorer's list / details / tile / thumbnail), a precondition that otherwise needs fragile menu clicking. `get_selection` returns `{items, can_select_multiple, is_required}`, `list_views` returns `{current, views}`, and `set_view` switches by view name. Dispatched through the injectable accessibility backend seam (headless-testable via a fake backend; real UIA in the Windows backend). No `PySide6`.

### Advanced TextPattern (find / select / read attributes)

Search a control's text, select a match to replace it, and read font/colour formatting. Full reference: [`docs/source/Eng/doc/new_features/v200_features_doc.rst`](docs/source/Eng/doc/new_features/v200_features_doc.rst).

- **`find_control_text` / `select_control_text` / `control_text_attributes`** (`AC_find_control_text`, `AC_select_control_text`, `AC_control_text_attributes`): `ax_text` shipped the three whole-range *reads*, but couldn't search for a substring, select a found range, or read text formatting — needed to assert "the error word is red and bold" or to place the selection at matched text before typing. This rounds out TextPattern: `find_control_text` searches the real content (not OCR) via `FindText`, `select_control_text` finds + selects a range so the next keystrokes replace it, and `control_text_attributes` reads `{font_name, font_size, bold, italic, foreground_color}`. Dispatched through the injectable accessibility backend seam (headless-testable via a fake backend; real UIA in the Windows backend). No `PySide6`.

### MSAA Bridge for Legacy Controls (LegacyIAccessible)

Automate the long tail of old Win32 controls that expose nothing via modern UIA. Full reference: [`docs/source/Eng/doc/new_features/v199_features_doc.rst`](docs/source/Eng/doc/new_features/v199_features_doc.rst).

- **`legacy_info` / `legacy_default_action`** (`AC_legacy_info`, `AC_legacy_default_action`): many legacy Win32 / MFC / Delphi controls expose nothing useful via modern UIA patterns (`control_get_value` / `control_invoke` / `control_toggle` all return None), yet they're fully described through the MSAA `IAccessible` bridge — Name, Value, Description, Role, State and a **DefaultAction**. This reads that info and fires the default action via `LegacyIAccessiblePattern` — the last-resort fallback that makes old apps automatable. Dispatched through the injectable accessibility backend seam (headless-testable via a fake backend; real UIA in the Windows backend). No `PySide6`.

### Move / Resize Elements + Window State (UIA Transform + Window)

Move a floating panel, resize a control, and know if a window is modal-blocked. Full reference: [`docs/source/Eng/doc/new_features/v198_features_doc.rst`](docs/source/Eng/doc/new_features/v198_features_doc.rst).

- **`move_element` / `resize_element` / `set_window_state` / `window_interaction_state`** (`AC_move_element`, `AC_resize_element`, `AC_set_window_state`, `AC_window_interaction_state`): this is UIA-**element-level**, not the HWND/title-level geometry in `window_layout`. `TransformPattern` moves/resizes a specific control or floating panel (dockable toolbars, MDI children, splitters) with no top-level window of its own; `WindowPattern` minimizes/maximizes a window and reports its **interaction state** (`ready` / `blocked_by_modal` / `not_responding`) — a reliable "is this window ready or modal-blocked?" signal pixel/title polling can't give. Dispatched through the injectable accessibility backend seam (headless-testable via a fake backend; real UIA in the Windows backend). No `PySide6`.

### Table Headers + Cell Addressing (UIA TablePattern)

Assert "the Status column of row 5 says Shipped" — by header, not by guessing indices. Full reference: [`docs/source/Eng/doc/new_features/v197_features_doc.rst`](docs/source/Eng/doc/new_features/v197_features_doc.rst).

- **`table_headers` / `table_cell` / `cell_by_header`** (`AC_table_headers`, `AC_table_cell`, `AC_cell_by_header`): `read_control_table` (GridPattern) dumps a flat 2-D list of cell names with no header labels and no way to address one cell by (header, row) — you can dump a grid but not test one. This adds the missing half: `table_headers` reads the row/column header labels (TablePattern), `table_cell` reads the cell at `(row, column)` with its span (GridItemPattern), and `cell_by_header` resolves the column index from the headers so you can read the cell at `(row, "Status")` directly. Dispatched through the injectable accessibility backend seam (headless-testable via a fake backend; real UIA in the Windows backend). No `PySide6`.

### Rich UIA Element Properties

Know if a control is enabled / off-screen / has a tooltip before you act. Full reference: [`docs/source/Eng/doc/new_features/v196_features_doc.rst`](docs/source/Eng/doc/new_features/v196_features_doc.rst).

- **`get_element_properties` / `is_element_enabled`** (`AC_get_element_properties`): the flat element list carries only name/role/bounds/app/id, but automation needs more before it acts — **is the control enabled** (don't click a disabled button), **is it off-screen**, its **item_status** (field validation/error), **help_text** (tooltip), and **accelerator_key** (drive via hotkey). This reads those high-value UIA properties (`enabled`/`offscreen`/`help_text`/`item_status`/`accelerator_key`/`access_key`/`orientation`); `is_element_enabled` is the common pre-action guard. Dispatched through the injectable accessibility backend seam (headless-testable via a fake backend; real UIA reads in the Windows backend). No `PySide6`.

### Realize Off-Screen Items in Virtualized Lists / Grids

Reach a row that isn't scrolled into view yet — the "element not found in a long list" fix. Full reference: [`docs/source/Eng/doc/new_features/v195_features_doc.rst`](docs/source/Eng/doc/new_features/v195_features_doc.rst).

- **`realize_item`** (`AC_realize_item`): long lists / data grids / trees only materialize visible rows, so an off-screen row has no accessibility element at all — `list_accessibility_elements` / `read_control_table` / `select_control_item` can't see it, and `scroll_control_into_view` can't help because the element doesn't exist yet. This locates the item by property (UIA `ItemContainerPattern.FindItemByProperty`) and realizes it (`VirtualizedItemPattern.Realize`) so it becomes a real, clickable element. Match `by` name (default) or `automation_id`; locate the container by name/role/app. Dispatched through the injectable accessibility backend seam (headless-testable via a fake backend; real UIA in the Windows backend). No `PySide6`.

### Per-Run Step Timeline (waterfall + bottleneck steps)

Read why *this* run was slow — a step waterfall and its bottlenecks. Full reference: [`docs/source/Eng/doc/new_features/v194_features_doc.rst`](docs/source/Eng/doc/new_features/v194_features_doc.rst).

- **`build_timeline` / `critical_steps`** (`AC_build_timeline`, `AC_critical_steps`): the action profiler aggregates timings by step *name* across runs — useless for "why was *this* run slow". This turns one run's ordered steps into a waterfall (each step's offset, duration, and `pct` share of the total) with the `bottleneck` step and a `parallelism` ratio (`> 1` when steps overlap via explicit `start` times); `critical_steps` ranks the dominant steps to optimise. A step is any `{name, duration, start?}` dict. Pure stdlib. No `PySide6`.

### Flaky-Test Co-Failure Clustering

Find the tests that flake *together* — and the shared root cause behind them. Full reference: [`docs/source/Eng/doc/new_features/v193_features_doc.rst`](docs/source/Eng/doc/new_features/v193_features_doc.rst).

- **`cofailure_pairs` / `failure_clusters`** (`AC_cofailure_pairs`, `AC_failure_clusters`): flaky tests are rarely independent — a wobbly fixture or noisy dependency makes a *group* fail in the same runs (~75% of flaky tests cluster). Ranking tests one-by-one by flip rate misses that. This measures how often each pair of tests fails in the *same* runs (Jaccard over their failing-run sets) and groups tests above a threshold into connected clusters with a cohesion score — so you chase one root cause instead of N symptoms. Input is a list of runs, each the test names that failed in it. Pure stdlib. No `PySide6`.

### Run-Trace Diff (what changed between two executions)

See exactly what changed between a passing run and a failing one. Full reference: [`docs/source/Eng/doc/new_features/v192_features_doc.rst`](docs/source/Eng/doc/new_features/v192_features_doc.rst).

- **`diff_runs` / `summarize_run_diff`** (`AC_diff_runs`): a run history says a run *failed* but not *what changed* from the run that passed. This aligns two step sequences with a longest-common-subsequence walk (so an inserted/removed step shifts the rest into place instead of mis-pairing everything) and classifies the differences: **added**/**removed** steps, **status_flips** (an aligned step that changed status — with the new failure's `failure_signature` when it carries an error), and **timing_regressions** (a step that got `regress_factor`× slower). `summarize_run_diff` renders a one-line summary. Pure stdlib over lists of `{name,status,duration,error}` step dicts. No `PySide6`.

### Stable Failure Signatures

Match the *same kind* of failure across runs, despite differing paths and ids. Full reference: [`docs/source/Eng/doc/new_features/v191_features_doc.rst`](docs/source/Eng/doc/new_features/v191_features_doc.rst).

- **`normalize_error` / `failure_signature` / `group_failures`** (`AC_failure_signature`, `AC_group_failures`): two runs that failed the same way rarely have byte-identical error text — paths, line numbers, addresses, ids and timestamps differ every time — which defeats "is this the same failure?" and "which tests fail together?". This strips the variable parts of an error to a canonical form and hashes it (SHA-256), so the same kind of failure gets the same short signature across runs — the join key the rest of the test-robustness tools (run diffing, flake clustering) group on. `group_failures` buckets a list of errors by signature, most frequent first. Pure stdlib (`re` + `hashlib`). No `PySide6`.

## What's new (2026-06-24)

### Visual Saliency (where to look — spectral-residual)

Find the region that stands out, with no template / colour / text. Full reference: [`docs/source/Eng/doc/new_features/v190_features_doc.rst`](docs/source/Eng/doc/new_features/v190_features_doc.rst).

- **`saliency_map` / `salient_regions` / `most_salient`** (`AC_salient_regions`, `AC_most_salient`): when there's no template, colour or text to key on, an agent still needs a cue for *where to look*. This computes the spectral-residual saliency map (Hou & Zhang 2007 — log amplitude minus its local average, reconstructed through the phase) and turns it into ranked salient boxes in source pixel coordinates. The transform is a pure numpy FFT (`cv2.saliency` is in the forbidden opencv-contrib package, so it's re-implemented over base opencv); it reuses `visual_match`'s grayscale loader and `cv2_utils.blobs.connected_boxes`. Regions threshold at `mean + 2·std` by default. A coarse attention cue to *narrow* where a template / OCR pass then looks. No `PySide6`.

### Display-Scale / Visual-DPI Detection

Infer which display scale (DPI) a template renders at — and how confidently. Full reference: [`docs/source/Eng/doc/new_features/v189_features_doc.rst`](docs/source/Eng/doc/new_features/v189_features_doc.rst).

- **`detect_scale` / `scale_sweep`** (`AC_detect_scale`, `AC_scale_sweep`): a template cropped at 100% scale won't match on a 150%-DPI machine, and `match_template` returns only the single best match — discarding the per-scale scores. This keeps the whole profile: `scale_sweep` scores the template at every scale, and `detect_scale` reports the winning scale as a DPI inference (`scale_percent`) with a confidence `margin` (how far it beats the runner-up). Reuses `visual_match._score_map` per scale; source is any ndarray / path / PIL image (or the live screen); scales default to the common Windows values. cv2/numpy lazily imported. No `PySide6`.

### Image Quality Scoring (sharpness / contrast / brightness gate)

Refuse to OCR a blurry or washed-out frame — score quality and gate before recognition. Full reference: [`docs/source/Eng/doc/new_features/v188_features_doc.rst`](docs/source/Eng/doc/new_features/v188_features_doc.rst).

- **`image_quality` / `is_blurry` / `quality_gate`** (`AC_image_quality`, `AC_quality_gate`): OCR and template matching quietly fail on a blurry, washed-out or too-dark capture, and the caller can't tell a *missing* element from an *unreadable* one. This measures sharpness (variance of the Laplacian), contrast (grayscale stddev) and brightness (mean 0–255); `quality_gate` turns them into `{passed, issues}` flagging `blurry` / `low_contrast` / `too_dark` / `too_bright` so a script can pre-process or re-capture before OCR. Reuses `visual_match`'s grayscale loader (any ndarray / path / PIL image, or the live screen); cv2/numpy lazily imported. No `PySide6`.

### Drop Files onto a Window (WM_DROPFILES)

Complete a drag-and-drop programmatically — drop files onto a target window. Full reference: [`docs/source/Eng/doc/new_features/v187_features_doc.rst`](docs/source/Eng/doc/new_features/v187_features_doc.rst).

- **`plan_file_drop` / `drop_files`** (`AC_plan_file_drop`, `AC_drop_files`): `clipboard_files` *stages* a file list on the clipboard for `Ctrl+V`; this actively **drops** files onto a target window by posting a `WM_DROPFILES` message. It reuses `clipboard_files.build_dropfiles` to pack the `DROPFILES` blob (shared byte layout, not re-implemented) and dispatches through an injectable driver seam, so the build-and-dispatch logic is unit-testable with a fake driver; the real `GlobalAlloc` + `PostMessage` lives in the default Win32 driver. `plan_file_drop` is a pure dry-run returning `{message, paths, point, wide, blob_size}`. No `PySide6`.

### Clipboard Format Inspection (classify / diff available formats)

See which formats are on the clipboard, and detect when its shape changes. Full reference: [`docs/source/Eng/doc/new_features/v186_features_doc.rst`](docs/source/Eng/doc/new_features/v186_features_doc.rst).

- **`classify_format` / `classify_formats` / `diff_formats` / `list_clipboard_formats` / `clipboard_formats`** (`AC_clipboard_formats`, `AC_classify_formats`, `AC_diff_formats`): the clipboard usually holds the same content in several formats at once (a Word copy = text + HTML + RTF; a file copy = CF_HDROP; a screenshot = CF_DIB). This enumerates the live clipboard (`EnumClipboardFormats`) without consuming anything and classifies each format into a friendly category (text/image/files/html/rtf/csv/audio/…); `diff_formats` is a pure monitor primitive returning `{added, removed, changed}` between two snapshots. The classifier and diff are pure (registered names take priority over dynamic ids); only the live enumeration is Win32. No `PySide6`.

### Rich Clipboard Formats (RTF and CSV/TSV)

Put styled text and tables on the clipboard for cross-app paste into Word and Excel. Full reference: [`docs/source/Eng/doc/new_features/v185_features_doc.rst`](docs/source/Eng/doc/new_features/v185_features_doc.rst).

- **`build_rtf` / `rtf_to_text` / `rows_to_csv` / `csv_to_rows` + `set_clipboard_rtf` / `get_clipboard_rtf` / `set_clipboard_csv` / `get_clipboard_csv`** (`AC_set_clipboard_rtf`, `AC_get_clipboard_rtf`, `AC_set_clipboard_csv`, `AC_get_clipboard_csv`): `rich_clipboard` added CF_HTML, but RTF (the format rich editors accept) and the `Csv` format Excel reads were still missing. This adds both: `build_rtf`/`rtf_to_text` build and strip RTF control words and `\uNNNN` / `\'XX` escapes in pure Python (fully unit-testable round-trip), and `rows_to_csv`/`csv_to_rows` wrap the stdlib `csv` module (delimiter-parametrised, so `\t` gives TSV). The codecs are platform-independent; the Win32 get/set share one generic byte-transfer helper, and the sets seed plain text so plain editors still paste. No `PySide6`.

### Keyboard Focus Order (Tab sequence / WCAG audit / set-focus)

Reason about keyboard navigation: the Tab order, a WCAG focus-order audit, and set-focus. Full reference: [`docs/source/Eng/doc/new_features/v184_features_doc.rst`](docs/source/Eng/doc/new_features/v184_features_doc.rst).

- **`is_interactive_role` / `tab_order` / `audit_focus_order` / `focus_control`** (`AC_tab_order`, `AC_audit_focus_order`, `AC_focus_control`): nothing reasoned about *keyboard* navigation — only mouse coordinates and element values. This adds the keyboard layer: `tab_order` returns the focusable elements in the order Tab visits them (reading order), `audit_focus_order` is a WCAG 2.4.x report (the sequence + flagged problems like a focusable element with no visible area), and `focus_control` sets keyboard focus via UIA `SetFocus`. The first three are pure functions over `AccessibilityElement` lists — `tab_order` reuses `element_parse.reading_order` and `is_interactive_role` reuses `ax_tree_walk.humanize_role`, so no logic is duplicated; `focus_control` dispatches the injectable backend seam (real `SetFocus` in the Windows backend). No `PySide6`.

### Readable, Addressable Accessibility Tree (role names + node paths)

Turn a raw `ControlType_50000` tree dump into readable roles with a stable path per node. Full reference: [`docs/source/Eng/doc/new_features/v183_features_doc.rst`](docs/source/Eng/doc/new_features/v183_features_doc.rst).

- **`control_type_name` / `humanize_role` / `humanize_tree` / `assign_node_paths` / `find_by_path`** (`AC_walk_tree`, `AC_humanize_role`): `dump_accessibility_tree` emits the platform's raw role (on Windows the bare UIA ControlType id, e.g. `ControlType_50000` for a button) and carries no stable per-node identity once serialised. This adds the pure post-processing it lacks: translate ControlType ids to friendly names, deep-copy a tree with every role humanised, stamp each node with a stable positional `path` (`"0.2.1"` — a pure stand-in for RuntimeId), and resolve a node back by path. `AC_walk_tree` is the readable counterpart to `AC_a11y_dump`. Pure-stdlib over `AXTreeNode`; unknown / non-UIA roles pass through unchanged. No `PySide6`.

### Native Text Reading via the UIA TextPattern (document / selection / visible)

Read the text in multiline editors and document controls where ValuePattern returns nothing. Full reference: [`docs/source/Eng/doc/new_features/v182_features_doc.rst`](docs/source/Eng/doc/new_features/v182_features_doc.rst).

- **`get_control_text` / `get_selected_text` / `get_visible_text`** (`AC_get_control_text`, `AC_get_selected_text`, `AC_get_visible_text`): `control_get_value` reads through UIA ValuePattern, which returns an empty string on multiline edits, RichEdit / document controls and web text areas — exactly the controls whose text you most want. This reads through `TextPattern` instead: `get_control_text` returns the whole `DocumentRange`, `get_selected_text` the current `GetSelection`, `get_visible_text` only the on-screen `GetVisibleRanges`. Dispatched through the injectable `accessibility.backends.get_backend()` seam (headless-testable via a fake backend; real UIA calls in the Windows backend), returning `{text}` from the executor/MCP. No `PySide6`.

### Extended UIA Control Patterns (Expand / Select / Range / Scroll)

Drive tree nodes, list/combo items, sliders and scroll natively, not by pixel guessing. Full reference: [`docs/source/Eng/doc/new_features/v181_features_doc.rst`](docs/source/Eng/doc/new_features/v181_features_doc.rst).

- **`expand_control` / `collapse_control` / `control_expand_state` / `select_control_item` / `control_range` / `set_control_range` / `scroll_control_into_view`** (`AC_expand_control`, `AC_select_control_item`, `AC_set_control_range`, …): the accessibility backend had only Value/Invoke/Toggle/Grid-read patterns, so treeviews, listboxes/combos, sliders and off-screen rows had no native call path. This adds ExpandCollapse / SelectionItem / RangeValue / ScrollItem patterns on top of the existing backend ABC, dispatched through the injectable `accessibility.backends.get_backend()` seam (headless-testable via a fake backend; real UIA calls in the Windows backend). No `PySide6`.

### Pre-Match Settle Gating + Match Persistence

Avoid matching mid-animation, and confirm a hit holds steady across frames. Full reference: [`docs/source/Eng/doc/new_features/v180_features_doc.rst`](docs/source/Eng/doc/new_features/v180_features_doc.rst).

- **`region_stability` / `match_persistence`** (`AC_region_stability`, `AC_match_persistence`): `smart_waits.wait_until_screen_stable` gates a live loop with a boolean — it can't score stability on an injectable frame sequence or check whether a *match* held steady. `region_stability` scores consecutive-frame SSIM (`{stable, mean_ssim, min_ssim}`); `match_persistence` confirms a template is found in *every* frame with the centres agreeing within `agree_px` (`{persisted, n_hits, jitter}`). Reuses `ssim` + `visual_match` + `grounding_consensus`; injectable frames; no `PySide6`.

### Colour-Aware Template Matching (HSV)

Tell a red status dot from a green one of identical shape. Full reference: [`docs/source/Eng/doc/new_features/v179_features_doc.rst`](docs/source/Eng/doc/new_features/v179_features_doc.rst).

- **`match_color` / `match_color_all`** (`AC_match_color`, `AC_match_color_all`): every `visual_match` matcher grayscales first, so red vs green of identical shape is indistinguishable; `color_region` finds known-colour blobs but can't template-match a multi-colour glyph. This matches on HSV hue/saturation with a colour-*distance* metric (`TM_SQDIFF_NORMED` — correlation would normalise away the absolute hue, scoring a red→green edge same as black→blue). Reuses `color_region`'s RGB loaders + `visual_match`'s resize/NMS/`Match`. `channels` default `("h","s")` (use `("h",)` for flat-saturation targets); for solid blobs use `find_color_region`. No `PySide6`.

### Multi-Template Consensus Matching

Vote several reference crops of one target into a single trustworthy location. Full reference: [`docs/source/Eng/doc/new_features/v178_features_doc.rst`](docs/source/Eng/doc/new_features/v178_features_doc.rst).

- **`match_ensemble` / `vote_centers`** (`AC_match_ensemble`, `AC_vote_centers`): a button renders in several states (default/hover/pressed) but is one logical target; `ab_locator` picks one strategy and `match_template(scales=...)` sweeps one template — neither fuses multiple references. This matches each reference, clusters the hit centres, and accepts a target only when ≥ `min_votes` agree within `agree_px`, returning `{point, votes, n_candidates, spread}` — cutting false positives on themed/animated UI. Reuses `visual_match.match_template` + `grounding_consensus`; `vote_centers` is the pure voting core. No `PySide6`.

### Per-Step Critic Features + Rule-Based Step Scorer

Bundle the evidence to score an agent step, with a built-in rule-based scorer. Full reference: [`docs/source/Eng/doc/new_features/v177_features_doc.rst`](docs/source/Eng/doc/new_features/v177_features_doc.rst).

- **`build_critic_record` / `score_step_rule_based` / `to_judge_prompt`** (`AC_build_critic_record`, `AC_score_step`): `trajectory_eval` scores a whole trajectory with no per-step evidence; `agent_trace` emits spans not quality; `agent_replay` stores steps but doesn't score. This composes `action_effect` + `observation_delta` + `postcondition` into one per-step record, then `score_step_rule_based` gives a deterministic `{outcome, process_score, reasons}` (no model needed) and `to_judge_prompt` renders it for an optional LLM-as-judge. Pure-stdlib aggregator; no `PySide6`.

### Heading vs Body Classification + Document Outline

Tell headings from body text by height and build a document outline. Full reference: [`docs/source/Eng/doc/new_features/v176_features_doc.rst`](docs/source/Eng/doc/new_features/v176_features_doc.rst).

- **`classify_lines` / `outline`** (`AC_classify_lines`, `AC_outline`): nothing mapped line height to heading levels or built a section outline — `ocr/structure` / `element_parse` are positional and `text_blocks` doesn't rank. This applies the standard heuristic: a line taller than `heading_ratio` × the median line height is a heading, and distinct heading heights become levels (tallest = 1). `classify_lines` tags each line `{box, text, role, level}`; `outline` returns the headings in order as a table of contents. Pure-stdlib over line dicts; no `PySide6`.

### Settle Detection Over a Churn Series

Decide when the UI has gone quiet — as a pure, testable function over a change series. Full reference: [`docs/source/Eng/doc/new_features/v175_features_doc.rst`](docs/source/Eng/doc/new_features/v175_features_doc.rst).

- **`settle_point` / `is_settled` / `SettleTracker`** (`AC_settle_point`): `smart_waits.wait_until_screen_stable` bakes the settle logic inside a `time.sleep` loop over live frames — you can't feed it a recorded series or unit-test the decision. This extracts it: given a stream of *churn* values (pixel delta / element-count delta / 0-1 digest-changed), it reports when churn stayed ≤ `max_churn` for `quiet_samples` in a row (a spike resets the run). `settle_point` returns the settle index, `SettleTracker` is the incremental form for a live loop. Pure-stdlib, no clock, no capture; no `PySide6`.

### Paragraph & List Grouping of OCR Lines

Group OCR lines into paragraphs and detect bulleted / numbered lists. Full reference: [`docs/source/Eng/doc/new_features/v174_features_doc.rst`](docs/source/Eng/doc/new_features/v174_features_doc.rst).

- **`group_paragraphs` / `detect_lists`** (`AC_group_paragraphs`, `AC_detect_lists`): `text_regions` merges glyphs into lines but nothing grouped those lines into paragraphs or detected lists; `ocr/structure` stops at flat rows. `group_paragraphs` starts a new paragraph wherever the vertical gap exceeds `line_gap_factor` × the median line height; `detect_lists` recognises bullet (`•`/`-`/`*`) or ordinal (`1.`/`2)`/`a.`) items, returning `{text, marker, indent, box}`. Pure-stdlib over line dicts; reuses `table_grid_fill`'s box reader; no `PySide6`.

### Column-Aware Reading Order (XY-Cut)

Read multi-column layouts down each column instead of interleaving them. Full reference: [`docs/source/Eng/doc/new_features/v173_features_doc.rst`](docs/source/Eng/doc/new_features/v173_features_doc.rst).

- **`flow_order` / `xy_cut` / `to_blocks`** (`AC_flow_order`, `AC_xy_cut`): `element_parse.reading_order` is a flat top-to-bottom sort that interleaves columns (reads A1, B1, A2, B2…). This recovers the correct order with recursive XY-cut — split at the widest whitespace valley (vertical → columns, horizontal → rows), so a two-column page reads A1, A2, B1, B2. `flow_order` returns the same `index`-tagged contract as `reading_order` (a drop-in column-aware upgrade, named to not shadow it); `xy_cut` exposes the region tree; `to_blocks` lists the leaf blocks. Pure-stdlib; no `PySide6`.

### Grounding Self-Consistency (Consensus Over Proposals)

Fuse several grounding proposals into one agreed target with an agreement score. Full reference: [`docs/source/Eng/doc/new_features/v172_features_doc.rst`](docs/source/Eng/doc/new_features/v172_features_doc.rst).

- **`consensus_point` / `consensus_element` / `is_confident`** (`AC_consensus_point`, `AC_consensus_element`): a target can be grounded several ways at once (set-of-marks / OCR / template / a11y / N model samples) and they don't always agree. `ab_locator`/`element_scoring` rank *strategies* by history; `snap_to_element` snaps a *single* coordinate — neither fuses *simultaneous* proposals. This clusters candidate points (or votes candidate elements), returns the agreed `point` + an `agreement` fraction + `spread`, and `is_confident` flags low-agreement targets so the agent zooms / asks instead of clicking blind. Pure-stdlib; no `PySide6`.

### Sub-Pixel Template-Match Refinement

Refine a match's centre to a fraction of a pixel for drag / slider / high-DPI precision. Full reference: [`docs/source/Eng/doc/new_features/v171_features_doc.rst`](docs/source/Eng/doc/new_features/v171_features_doc.rst).

- **`match_subpixel` / `refine_peak`** (`AC_match_subpixel`): every matcher returns *integer* coordinates from `cv2.minMaxLoc` — for a drag handle, fine slider or high-DPI display that rounding is the dominant click-placement error. This fits a parabola to the 3×3 score neighbourhood around the peak (independently on x/y, the standard NCC sub-pixel method) and returns a `SubPixelMatch` with float `cx`/`cy` + the applied `offset_x`/`offset_y`. Reuses `visual_match._score_map`; injectable `haystack`; no `PySide6`.

### Repair-Tactic Policy for Failed / No-Effect Actions

Pick the next repair tactic when an action does nothing — and drive the retry loop. Full reference: [`docs/source/Eng/doc/new_features/v170_features_doc.rst`](docs/source/Eng/doc/new_features/v170_features_doc.rst).

- **`plan_repair` / `next_tactic` / `run_with_repair`** (`AC_plan_repair`): `self_healing`/`locator_repair` only fix a locator that *didn't resolve*; `loop_guard` only *detects* a stuck loop with no tactic selection. This consumes an effect verdict (e.g. from `action_effect`) and returns the ordered tactics to try — `wait_retry` / `relocate` / `nudge` / `scroll_into_view` / `escalate` — then `run_with_repair` drives a bounded retry loop with injected `act` / `verify` / `apply_tactic` / `verdict_for` / `sleep` seams, returning a `RepairOutcome`. Pure-stdlib state machine; no `PySide6`. Completes the self-correction trio with `action_effect` + `postcondition`.

### Declarative Action Postconditions

Assert an action's expected outcome as a JSON spec, diffed against the before-frame. Full reference: [`docs/source/Eng/doc/new_features/v169_features_doc.rst`](docs/source/Eng/doc/new_features/v169_features_doc.rst).

- **`check_postcondition` / `compile_postcondition`** (`AC_check_postcondition`): `expect_poll`/`assert_eventually` poll a single condition with no action-bound spec and no before-baseline (so they can't express "a *new* dialog appeared"); `trajectory_eval` is whole-trajectory. This evaluates a small JSON spec of clauses — `appears`/`disappears` (diffed vs `before`), `enabled`/`disabled`, `text_present`/`text_absent`, `count` — against the after-observation, returning a per-clause `{ok, clauses, failed}` report. `compile_postcondition` turns a spec into an `after -> bool` predicate for `expect_poll`. Pure-stdlib; no `PySide6`.

### Edge-Shape (Chamfer) Template Matching

Locate flat icons by outline, robust to fill / theme / anti-aliasing. Full reference: [`docs/source/Eng/doc/new_features/v168_features_doc.rst`](docs/source/Eng/doc/new_features/v168_features_doc.rst).

- **`edge_match` / `edge_match_all` / `chamfer_distance`** (`AC_edge_match`, `AC_edge_match_all`): intensity NCC (`visual_match`) drops when a control is re-filled / re-themed, and ORB (`feature_match`) needs corner texture flat-design glyphs lack. This matches by *edge shape*: Canny both images, distance-transform the scene edges, slide the template's edges over it and score by mean edge-to-edge distance (Chamfer). A perfect outline aligns at ~0 cost regardless of fill. Reuses `visual_match`'s loaders / resize / NMS / `Match` and `edge_lines`'s Canny default. Injectable `haystack`; no `PySide6`.

### Action-Effect Classification (Did My Click Do Anything?)

Tell an agent whether a click did anything — and whether it happened where it aimed. Full reference: [`docs/source/Eng/doc/new_features/v167_features_doc.rst`](docs/source/Eng/doc/new_features/v167_features_doc.rst).

- **`classify_effect` / `effect_near_point` / `is_no_op`** (`AC_classify_effect`, `AC_effect_near_point`): `screen_state`/`element_diff` report what changed but never tie it to the action; `loop_guard` only flags a no-op after N repeats. This diffs the before/after observation and, given the action's target point, classifies the result on the *first* step as `no_op` / `changed_near_target` / `changed_elsewhere` (a surprise dialog) / `changed`, returning an `EffectVerdict` with the changed centres and a reason. Reuses `element_diff.match_elements` + `observation_delta`'s field-change check. Pure-stdlib; no `PySide6`.

### Form Field Association (Multi-Direction) + Checkbox State

Pair form labels with values even when the value is below or right-aligned, and read checkbox state. Full reference: [`docs/source/Eng/doc/new_features/v166_features_doc.rst`](docs/source/Eng/doc/new_features/v166_features_doc.rst).

- **`associate_fields` / `match_labels_to_widgets` / `checkbox_state`** (`AC_associate_fields`, `AC_match_labels_to_widgets`): `ocr/structure` only pairs a `label:` with the *immediately next* cell — it can't handle label-above-value, two-column key/value, right-aligned values, or non-text widgets, and has no checkbox notion. This pairs each label with the nearest aligned value across *directions* (right / below) within `max_gap`, matches free-standing widgets (checkbox/radio/input) to their nearest label, and reads checkbox state from the box's dark-pixel fill ratio. Association is pure-stdlib; only `checkbox_state` touches pixels (behind the `visual_match` gray loader). No `PySide6`.

### Whitespace-Projection Columns (Borderless Tables)

Read borderless tables by inferring columns from the whitespace gaps. Full reference: [`docs/source/Eng/doc/new_features/v165_features_doc.rst`](docs/source/Eng/doc/new_features/v165_features_doc.rst).

- **`detect_borderless_table` / `column_gutters` / `assign_columns` / `vertical_projection`** (`AC_detect_borderless_table`, `AC_column_gutters`): `ocr/structure` only detects a table when every row's cell-left-x matches — it fails on ragged / borderless / right-aligned columns; `edge_lines.find_grid` needs ruling lines a whitespace table doesn't have. This finds columns by the *gaps*: project OCR boxes onto the x-axis, read the persistent empty vertical bands as gutters, assign column indices, bucket rows by spacing, and emit `{n_rows, n_cols, rows, columns}`. Pure-stdlib difference-array projection (no numpy); reuses `table_grid_fill`'s box reader. No `PySide6`.

### Auto-Thresholded Template Matching (Otsu on the Score Map)

No more hand-tuned `min_score` — derive the match threshold from the score map. Full reference: [`docs/source/Eng/doc/new_features/v164_features_doc.rst`](docs/source/Eng/doc/new_features/v164_features_doc.rst).

- **`match_auto` / `auto_threshold`** (`AC_match_auto`, `AC_auto_threshold`): every `match_template_all` call forces you to guess `min_score` (too low floods NMS, too high drops re-themed targets, and it differs per asset). This runs Otsu on the *correlation score histogram* to find the valley between background correlation and real matches, returns that cut-off plus a *separability* score (near 0 = unimodal, no clear match → don't trust it). `match_auto` returns one peak per above-threshold region (via `connected_boxes`, avoiding duplicate hits on a wide peak), clamped by a `floor`. Reuses the new `visual_match._score_map`; injectable `haystack`; no `PySide6`.

### Token-Budgeted Observation Delta (What Changed)

Tell an agent *what changed* since the last step, not the whole screen again. Full reference: [`docs/source/Eng/doc/new_features/v163_features_doc.rst`](docs/source/Eng/doc/new_features/v163_features_doc.rst).

- **`delta_observation` / `delta_index` / `summarize_delta`** (`AC_delta_observation`): `serialize_observation` renders one full frame (blows the token budget every turn); `element_diff` gives the stable-ID correspondence but stops at matched/added/removed element pairs. This is the missing serializer — it diffs two frames, classifies matched elements as changed (role/name/enabled/value/moved) or stable, and renders only the churn as `+ [i] role "name"` / `~ [i] … (fields)` / `- …` lines (added & changed first, stable dropped, capped at `max_lines`). Reuses `element_diff.match_elements` + `observation.observation_index`. Pure-stdlib; no `PySide6`.

### Fill a Ruling-Line Grid With OCR Text (Addressable Tables)

Turn a bordered table's lines + OCR words into an addressable `R x C` table. Full reference: [`docs/source/Eng/doc/new_features/v162_features_doc.rst`](docs/source/Eng/doc/new_features/v162_features_doc.rst).

- **`populate_table` / `assign_text_to_grid` / `table_to_records` / `table_to_csv`** (`AC_populate_table`): `edge_lines.find_grid` recovers a table's ruling-line geometry but the cells come back *empty*; OCR gives the text but no structure — nothing joined them. This drops OCR boxes into the grid (assigned by cell-centre, gated by an overlap fraction so a box straddling a thin rule isn't double-counted), concatenates each cell's text in reading order, flags merged-cell spans, and converts straight to records / CSV. Pure-stdlib over plain dicts — no image, no OCR engine, no device. No `PySide6`.

### Trust-Scored Template Matching (Ambiguity / PSR)

Know when a template match is strong but *ambiguous* before clicking it. Full reference: [`docs/source/Eng/doc/new_features/v161_features_doc.rst`](docs/source/Eng/doc/new_features/v161_features_doc.rst).

- **`match_with_trust` / `score_peaks`** (`AC_match_with_trust`): `match_template` returns only the top score and clicks it — but a button repeated in a toolbar or a near-identical sibling correlates ~0.95 in two places, so a high score is not an *unambiguous* match. This adds a Lowe-style ratio test *for pixel templates* (ORB got one via `feature_match`; `match_template` never did): it inspects the whole correlation surface, compares the global peak to the next-best peak outside an exclusion window, computes the peak-to-sidelobe ratio (PSR), and returns a `TrustedMatch` with `second_score` / `peak_ratio` / `psr` / `is_ambiguous`. Reuses a new `visual_match._score_map` (the full `matchTemplate` surface the public matchers discard) — no matching code duplicated. Injectable `haystack`; no `PySide6`.

## What's new (2026-06-23)

### Clipboard File-Drop List (CF_HDROP)

Put a list of files on the clipboard, ready to paste into Explorer. Full reference: [`docs/source/Eng/doc/new_features/v160_features_doc.rst`](docs/source/Eng/doc/new_features/v160_features_doc.rst).

- **`build_dropfiles` / `parse_dropfiles` / `set_clipboard_files` / `get_clipboard_files`** (`AC_set_clipboard_files`, `AC_get_clipboard_files`): the clipboard carried text, images and (via `rich_clipboard`) HTML, but never a *file list* — the `CF_HDROP` payload Explorer reads to paste files as a real copy. Building it is fiddly (20-byte `DROPFILES` header + double-null-terminated UTF-16 path list + `pFiles` offset). This isolates the packing into pure, fully testable `build_dropfiles` / `parse_dropfiles` byte functions, with thin Windows-only `set`/`get_clipboard_files` wrappers on top — the same split `rich_clipboard` uses for `CF_HTML`. No `PySide6`.

### Coarse Labelled Screen Grid (VLM Grounding)

Refer to screen regions as grid cells ("click C3") instead of raw pixels. Full reference: [`docs/source/Eng/doc/new_features/v159_features_doc.rst`](docs/source/Eng/doc/new_features/v159_features_doc.rst).

- **`grid_cells` / `cell_for_point` / `point_for_cell`** (`AC_grid_cells`, `AC_cell_for_point`, `AC_point_for_cell`): VLM grounding is far more reliable when a model names a coarse cell than when it emits hallucinated pixel coordinates. This lays an `rows`x`cols` grid over the screen (or a `region`), labels each cell spreadsheet-style (`A1` top-left, past `Z` → `AA`), and maps both ways — point → containing cell, named cell → centre point (ready to click). Pure-stdlib geometry; the only device-bound path is the default that reads the live screen size, so every function is headless-testable with an explicit `region`. No `PySide6`.

### Rotation- & Scale-Tolerant Template Matching

Find templates that are rotated or skewed, not just scaled. Full reference: [`docs/source/Eng/doc/new_features/v158_features_doc.rst`](docs/source/Eng/doc/new_features/v158_features_doc.rst).

- **`match_rotated` / `match_rotated_all` / `scale_space`** (`AC_match_rotated`, `AC_match_rotated_all`): `match_template` sweeps *scales* but assumes axis-aligned — OpenCV's `matchTemplate` isn't rotation-invariant, so a skewed control, a rotated icon or a dial at a different angle is missed. This sweeps `angles` (each warped with `cv2.warpAffine`) crossed with a `np.linspace` scale-space, returns the best-correlating `RotatedMatch` carrying the recovered `scale` + `angle` (the `*_all` form NMS-dedupes neighbouring angles/scales). Reuses `visual_match`'s loaders / resize / method table / NMS — no matching or geometry code duplicated. Injectable `haystack`; headless-testable; no `PySide6`.

### Barcode Decoding (1-D)

Read EAN / UPC / Code-128 barcodes off the screen or an image. Full reference: [`docs/source/Eng/doc/new_features/v157_features_doc.rst`](docs/source/Eng/doc/new_features/v157_features_doc.rst).

- **`read_barcodes`** (`AC_read_barcodes`): the framework decoded QR codes (`read_qr`) but had no reader for the *1-D* barcodes (EAN-13/8, UPC-A, Code-128) that label physical goods, inventory tickets and shipping labels. This decodes them via OpenCV's `cv2.barcode.BarcodeDetector`, returning `{text, type, points}` per code. The decode step is an injectable seam (default calls OpenCV; tests pass their own `decoder`), so it's fully headless-testable and degrades gracefully — an OpenCV build without the `barcode` module returns `[]` instead of raising. Reuses the shared `visual_match` haystack loader; no `PySide6`.

### Weighted Candidate Scoring

Rank ambiguous element candidates by a confidence score. Full reference: [`docs/source/Eng/doc/new_features/v156_features_doc.rst`](docs/source/Eng/doc/new_features/v156_features_doc.rst).

- **`score_candidates` / `best_candidate`** (`AC_score_candidates`, `AC_best_candidate`): `anchor_locator` is a single relation + distance sort and `ab_locator` races whole strategies by elapsed time — neither ranks ambiguous candidates by a *weighted* mix of role match + fuzzy name similarity + anchor proximity + enabled-state. This returns `ScoredCandidate`s best-first with a `matched_on` breakdown; the name similarity is injectable (default `fuzzy_ratio`, reused — no new string-distance code). Pure-stdlib over element dicts; powers self-heal / grounding when several boxes could be the target. Headless-testable.

### Geometry-Aware Element Diff & Stable IDs

Track elements across frames by overlap, with stable IDs. Full reference: [`docs/source/Eng/doc/new_features/v155_features_doc.rst`](docs/source/Eng/doc/new_features/v155_features_doc.rst).

- **`match_elements` / `assign_stable_ids`** (`AC_match_elements`, `AC_assign_stable_ids`): `diff_snapshots` keys identity on `(role, name)` — it can't match a renamed-but-stationary control or a moved one, nor give persistent IDs across frames. This matches element boxes by IoU (reusing `element_parse.iou`): `match_elements` returns `{matched, added, removed}`; `assign_stable_ids` carries each element's `id` from a `prior` frame (a moved button keeps its id, a new one gets a fresh id) — so an agent can reliably refer to "element 7" turn-over-turn. Pure-stdlib, headless-testable.

### Portable Agent-Trajectory Trace (Record & Replay)

Log an agent's observation→action steps and replay them. Full reference: [`docs/source/Eng/doc/new_features/v154_features_doc.rst`](docs/source/Eng/doc/new_features/v154_features_doc.rst).

- **`record_step` / `to_jsonl` / `from_jsonl` / `replay_trace`** (`AC_replay_trace`): `agent_trace` records OTel spans (observability), `trajectory_eval` only scores, `semantic_recording` replays human macros — none is a replayable obs→action transcript. This is the OmniTool-style `{step, observation, action, result}` JSONL with a deterministic replay driver (injectable `runner`, no live model). The executor command replays each step's AC action through the executor. Pure-stdlib, headless-testable; build regression / training datasets from agent runs.

### Pre-Action Grounding Guard

Reject out-of-bounds clicks; snap near-misses onto the real element. Full reference: [`docs/source/Eng/doc/new_features/v153_features_doc.rst`](docs/source/Eng/doc/new_features/v153_features_doc.rst).

- **`validate_action` / `snap_to_element` / `in_bounds`** (`AC_validate_action`): `guardrail` scans text and `loop_guard` detects loops — neither validates a coordinate action before dispatch, so a hallucinated `(9999,-5)` click fires into nothing and a 5px-off click misses. This rejects off-screen coordinates and, given `targets`, snaps a near-miss onto the nearest element's centre, returning `{ok, reason, snapped}`. Pure-stdlib geometry over element dicts; the executor `screen` defaults to the live screen. Headless-testable; plugs in front of an agent loop's dispatch.

### Token-Budgeted A11y Text Observation

Turn the a11y tree into an indexed text block a VLM can act on. Full reference: [`docs/source/Eng/doc/new_features/v152_features_doc.rst`](docs/source/Eng/doc/new_features/v152_features_doc.rst).

- **`serialize_observation` / `observation_index` / `flatten_tree`** (`AC_serialize_observation`, `AC_observation_index`): `describe_screen` gives role *counts* + a flat label list — no stable index, no `[12] button "Submit" @(x,y)` lines, no viewport clip, no token budget. This flattens a (nested) element tree to interactive-only, clips to the viewport, orders reading-style, caps at `max_elements`, assigns a stable `index`, and renders the lines a model acts on ("click [12]"). Pure-stdlib over element dicts; pairs with `fuse_elements`/`set_of_marks`. Headless-testable.

### Canonical Computer-Use Action Schema

Bridge Anthropic / OpenAI agent actions to AutoControl commands. Full reference: [`docs/source/Eng/doc/new_features/v151_features_doc.rst`](docs/source/Eng/doc/new_features/v151_features_doc.rst).

- **`from_anthropic` / `from_openai_cua` / `to_ac_command` / `canonical_action`** (`AC_cua_command`): `tool_use_schema` exports AC_* signatures and `coordinate_space` rescales — neither *normalizes an inbound action payload*. Anthropic emits `{action:"left_click", coordinate:[x,y]}`, OpenAI CUA emits `{type:"click", x, y, button}`; these adapters map both to a canonical action and then to a runnable `[AC_*, params]` (with optional coordinate-space `scale`). Pure-stdlib, headless-testable; the executor command returns `{canonical, command}` for any source.

### Window Client-Area Geometry

Click *inside* a window regardless of its title bar / borders. Full reference: [`docs/source/Eng/doc/new_features/v150_features_doc.rst`](docs/source/Eng/doc/new_features/v150_features_doc.rst).

- **`get_client_rect` / `client_point` / `frame_insets` / `client_to_screen`** (`AC_get_client_rect`, `AC_client_point`): `get_window_geometry` returns only the *outer* bbox — there was no client-area rect, frame-inset math, or client→screen mapping. `client_point("App", x, y)` maps a content-relative point to the screen so a click lands inside the window regardless of chrome; `frame_insets` reports border/title-bar thickness. `frame_insets`/`client_to_screen` are pure geometry (headless-testable); `get_client_rect` uses an injectable Win32 reader (`GetClientRect`+`ClientToScreen`).

### Perceptual (YIQ) Image Diff with Anti-Alias Suppression

Visual-regression diffing that ignores anti-aliased edges. Full reference: [`docs/source/Eng/doc/new_features/v149_features_doc.rst`](docs/source/Eng/doc/new_features/v149_features_doc.rst).

- **`perceptual_diff` / `assert_perceptual`** (`AC_perceptual_diff`): `image_difference` counts raw per-channel deltas and `ssim_compare` is a global score — neither uses a perceptual metric or ignores anti-aliasing, the #1 source of false-positive visual-diff failures. This compares in YIQ space (pixelmatch's colour metric) and, by default, removes thin 1px anti-aliased edge diffs via a morphological open so only solid changes count (`include_aa=True` keeps them). Returns `{diff_pixels, diff_ratio, regions}`; `assert_perceptual` / `max_diff_ratio` gate a regression test. Injectable image pair → headless-testable (a 1px fringe → 0, a solid block → counted).

### Soft Assertions (Aggregate Failures)

Verify many things, report every failure at once. Full reference: [`docs/source/Eng/doc/new_features/v148_features_doc.rst`](docs/source/Eng/doc/new_features/v148_features_doc.rst).

- **`SoftAssertions`** (`AC_soft_assert`): `assert_all` takes a pre-built spec list up front — there was no scoped accumulator you sprinkle `check()` calls into that raises everything on block exit (JUnit5 `assertAll` / Playwright `expect.soft`). `with SoftAssertions() as soft: soft.check(...)` records pass/fail (never raising mid-block, returns the bool to branch on), then raises once on exit listing every failure — and never masks an exception already propagating. The executor command aggregates a JSON `checks` list (eq/ne/gt/lt/contains/truthy). Pure-stdlib, headless-testable.

### Window Z-Order (Always-On-Top / Front / Back)

Pin a window on top, raise it, or push it behind. Full reference: [`docs/source/Eng/doc/new_features/v147_features_doc.rst`](docs/source/Eng/doc/new_features/v147_features_doc.rst).

- **`set_topmost` / `bring_to_front` / `send_to_back` / `plan_zorder`** (`AC_set_topmost`, `AC_bring_to_front`, `AC_send_to_back`): the raw `set_window_position` existed but wasn't in the facade, had no title wrapper and no topmost semantics — the standard RPA "always-on-top" was missing. `plan_zorder` is a pure action→`SetWindowPos` constant lookup (headless-testable); the title-based setters apply it through an injectable driver (the `snap_window` seam pattern), Win32 by default. 

### Localized Motion / Activity Detection

Find which sub-regions are animating between two frames. Full reference: [`docs/source/Eng/doc/new_features/v146_features_doc.rst`](docs/source/Eng/doc/new_features/v146_features_doc.rst).

- **`changed_regions` / `has_motion` / `activity_score`** (`AC_changed_regions`, `AC_has_motion`): `wait_until_screen_stable` is a boolean poll, `ssim_changed_regions` is structural (ignores fast motion), `diff_screenshots` isn't activity blobs. This is the cheap absdiff path — threshold the per-pixel difference, dilate, and return the moved-region boxes (largest first), a boolean, and the fraction of pixels that moved. Pick a quiet area or locate a spinner. Two injectable frames → headless-testable; reuses the shared connected-components helper; `after` defaults to a live screen grab in the executor.

### Colour-Histogram Fingerprint & Change Detection

Tell whether the view is "the same" despite lighting / scale. Full reference: [`docs/source/Eng/doc/new_features/v145_features_doc.rst`](docs/source/Eng/doc/new_features/v145_features_doc.rst).

- **`image_histogram` / `compare_histograms` / `histogram_changed`** (`AC_image_histogram`, `AC_histogram_changed`): `image_dedup`'s perceptual hash is spatial (brittle to colour/theme) and `color_stats` is one colour. A normalized colour histogram is the illumination/scale-robust "same view, or palette shifted?" signal (theme switch, reload, rotated banner). `image_histogram` returns a per-channel histogram (`hsv`/`rgb`/`gray`); `compare_histograms` does correlation/chisqr/intersection/bhattacharyya; `histogram_changed` compares a reference vs the live screen. Injectable image → headless-testable; base OpenCV (`cv2.calcHist`/`compareHist`).

### Rich Clipboard (HTML / CF_HTML)

Copy and paste *formatted* HTML into Word / Outlook. Full reference: [`docs/source/Eng/doc/new_features/v144_features_doc.rst`](docs/source/Eng/doc/new_features/v144_features_doc.rst).

- **`build_cf_html` / `parse_cf_html` / `set_clipboard_html` / `get_clipboard_html`** (`AC_set_clipboard_html`, `AC_get_clipboard_html`): the base clipboard handles plain text + image only — rich paste needs `CF_HTML`, whose byte-offset header (`StartHTML`/`EndHTML`/`StartFragment`/`EndFragment`) is famously error-prone. `build_cf_html`/`parse_cf_html` compute and recover it in pure Python (round-trip tested, correct across multi-byte UTF-8); `set/get_clipboard_html` wrap them over the Win32 clipboard (with a plain-text fallback). Byte-offset math is headless-testable; only the I/O is Windows.

### Composable / Filtered Candidate Locators

Refine located elements with a chain: `.within(panel).filter(has_text="Delete").nth(1)`. Full reference: [`docs/source/Eng/doc/new_features/v143_features_doc.rst`](docs/source/Eng/doc/new_features/v143_features_doc.rst).

- **`from_boxes` / `Candidates`** (`AC_locate_chain`): `anchor_locator` is a single relation and `grid_locator` is cells — neither supports composable refinement of a candidate set (the Selenium-4 / Playwright chained-locator idiom). This is a pure post-filter over boxes from *any* source (template / OCR / a11y / `fuse_elements`): `within` (region clip), `filter` (`has_text` / `near` / area / predicate), `sort_reading`, `nth` / `first` / `last`, `resolve()` / `center()`. Every method returns a new `Candidates` (no mutation) → fully headless-testable. The executor command applies a JSON `ops` list.

### Retrying Value Assertions (expect.poll)

Retry *any* value until it matches, not just the built-in checks. Full reference: [`docs/source/Eng/doc/new_features/v142_features_doc.rst`](docs/source/Eng/doc/new_features/v142_features_doc.rst).

- **`expect_poll` / `assert_poll` + matchers** (`AC_expect_poll`): `assert_eventually` only polls the fixed dict-spec checks (text/image/pixel/…). This polls any zero-arg `getter` against any `matcher` (`to_equal` / `to_contain` / `to_be_greater_than` / `to_match_regex` / `to_be_truthy` / `to_be_stable`) until it passes or times out — an OCR'd total, a row count stabilising, a custom predicate. Injectable `clock`/`sleep` → deterministic, mirrors Playwright's `expect.poll`. The executor command re-runs a nested action until a key of its result matches.

### Line / Grid / Separator Detection (Hough)

Find table grid lines and UI dividers from raw pixels. Full reference: [`docs/source/Eng/doc/new_features/v141_features_doc.rst`](docs/source/Eng/doc/new_features/v141_features_doc.rst).

- **`find_lines` / `find_grid` / `find_separators`** (`AC_find_lines`, `AC_find_grid`, `AC_find_separators`): `grid_locator` clusters *already-found* boxes and `shape_locator` finds closed rectangles — neither finds a table's ruling lines or a divider from pixels. Canny + probabilistic Hough detects straight segments (classified horizontal/vertical/diagonal), `find_grid` recovers `{rows, cols, cells}` so you can address "row 3, col 2", and `find_separators` returns the coordinates of long dividers. Injectable haystack → headless-testable; base OpenCV (`cv2.HoughLinesP`).

### Model-Free Text-Region Detection (MSER)

Find where text is on screen without running OCR. Full reference: [`docs/source/Eng/doc/new_features/v140_features_doc.rst`](docs/source/Eng/doc/new_features/v140_features_doc.rst).

- **`find_text_regions` / `find_text_lines`** (`AC_find_text_regions`, `AC_find_text_lines`): `shape_locator` finds rectangles (not text) and `locate_text` needs an OCR engine *and* the exact string — neither answers "where is *any* text?". MSER finds the glyph/word/line blobs, so a script can crop candidate boxes to feed OCR (faster + more accurate than full-frame) or detect a label appeared with no OCR dependency. `merge` unions MSER's nested per-glyph regions; `find_text_lines` groups glyphs into per-line boxes; a blank screen returns `[]`. Base OpenCV (`cv2.MSER_create`), injectable haystack → headless-testable.

### HSV Colour-Space Segmentation

Find "any shade of red" regardless of lighting. Full reference: [`docs/source/Eng/doc/new_features/v139_features_doc.rst`](docs/source/Eng/doc/new_features/v139_features_doc.rst).

- **`dominant_hue_regions` / `segment_hsv` / `color_mask`** (`AC_dominant_hue_regions`, `AC_segment_hsv`): `find_color_region` masks in RGB with a per-channel ± box — it can't match "the same colour at a different brightness" (status lights, highlights, theme tints). HSV separates hue from brightness, so a hue band + saturation/value floor catches every shade across lighting. `dominant_hue_regions(hue=…)` handles red's 0/180 wrap automatically; `segment_hsv` takes an explicit band; both return `{x,y,width,height,area,center}` blobs reusing the shared connected-components helper. Injectable haystack → headless-testable.

### Fuse & Order On-Screen Element Boxes

Turn raw OCR + icon + a11y boxes into one clean, numbered element list. Full reference: [`docs/source/Eng/doc/new_features/v138_features_doc.rst`](docs/source/Eng/doc/new_features/v138_features_doc.rst).

- **`iou` / `merge_boxes` / `fuse_elements` / `reading_order`** (`AC_fuse_elements`, `AC_reading_order`): `set_of_marks` numbers a clean element list but nothing *produced* it — a real screen parse yields three overlapping sources with duplicates and no order. These supply the missing step: drop near-duplicate boxes by IoU, union OCR/icon/a11y keeping the most trustworthy source on overlap (`source_priority` a11y > ocr > icon), and sort top-to-bottom/left-to-right with a stable `index`. Plain `dict` boxes → pure-stdlib, fully headless-testable; pairs directly with `set_of_marks`.

### Actionability Gate (Wait Until Ready Before Acting)

Don't click until the target is genuinely ready. Full reference: [`docs/source/Eng/doc/new_features/v137_features_doc.rst`](docs/source/Eng/doc/new_features/v137_features_doc.rst).

- **`wait_actionable` / `act_when_ready`** (`AC_wait_actionable`): Playwright/Cypress run an actionability check before every click — present + stopped moving + enabled + not covered — but AutoControl had none (`self_heal_click` clicks immediately; `wait_until_screen_stable` watches the whole frame). This composes the four checks into one gate and returns an `ActionabilityReport` (per-check booleans, target `point`, `reason` = first failing check). Every signal is an injectable callable (`bbox_provider` / `region_sampler` / `enabled_probe` / `hit_tester`) plus an injectable `clock`/`sleep`, so it's fully deterministic and headless-testable. The executor command gates on a template image.

### Multi-Monitor / Virtual-Desktop Geometry

Place windows and points correctly across several displays. Full reference: [`docs/source/Eng/doc/new_features/v136_features_doc.rst`](docs/source/Eng/doc/new_features/v136_features_doc.rst).

- **`enumerate_monitors` + `Monitor` / `virtual_bounds` / `monitor_at_point` / `monitor_for_window` / `to_local` / `to_virtual` / `remap_point`** (`AC_enumerate_monitors`, `AC_monitor_at_point`): `snap_window` / `arrange_grid` / the layout planner all assumed a single primary `(width, height)` — monitor-blind, unable to tile on a second display or handle a negative-origin virtual desktop. This adds the physical layer: union virtual bounds, which-monitor-owns-this-point/window, virtual↔monitor-local conversion, and equivalent-spot remapping across resolutions/DPI. Pure geometry over `Monitor` dataclasses → fully headless-testable; `enumerate_monitors` has an injectable provider (default `mss`).

### Image Pre-processing for OCR / Template Matching

Clean up the screen before reading or matching it. Full reference: [`docs/source/Eng/doc/new_features/v135_features_doc.rst`](docs/source/Eng/doc/new_features/v135_features_doc.rst).

- **`preprocess_image` + `to_grayscale` / `binarize` / `upscale` / `denoise` / `deskew` / `enhance_contrast`** (`AC_preprocess_image`): `locate_text` and `match_template` fed the *raw* capture to OCR / the matcher — small text, dark themes, low contrast and skew wrecked both, with no preprocessing seam anywhere. This adds the standard pipeline (grayscale → upscale → binarize → deskew → denoise → CLAHE) that multiplies their accuracy. Injectable haystack → ndarray; `detect_skew_angle` measures text rotation; `binarize` does otsu / adaptive. The executor command writes the cleaned image to a path. Headless-testable on synthetic arrays.

### Arrange Multiple Windows (Grid / Cascade)

Lay out a whole set of windows in one call. Full reference: [`docs/source/Eng/doc/new_features/v134_features_doc.rst`](docs/source/Eng/doc/new_features/v134_features_doc.rst).

- **`arrange_grid` / `arrange_cascade`** (`AC_arrange_grid`, `AC_arrange_cascade`): `snap_window` moves *one* window and the layout planner only *computes* rectangles — these close the loop, taking a list of window titles and actually moving every match into a grid (auto near-square shape, or explicit `rows`/`cols` + `gap`) or a diagonal cascade. Build on the layout planner and reuse `snap_window`'s injectable `mover`/`screen_size` seams, so they are fully headless-testable; return the count moved.

### Window Tiling / Layout Geometry Planner

Compute where to place application windows — halves, grids, cascades. Full reference: [`docs/source/Eng/doc/new_features/v133_features_doc.rst`](docs/source/Eng/doc/new_features/v133_features_doc.rst).

- **`tile_rect` / `grid_rects` / `cascade_rects`** (`AC_tile_rect`, `AC_grid_rects`, `AC_cascade_rects`): `save/restore_window_layout` replay *exact* saved positions and `snap_window` moves *one* window — nothing *computes* a fresh multi-window layout. This pure-geometry planner returns the target rectangles for halves, quadrants, thirds, an R×C grid and a staggered cascade given a screen work area, so a script can lay out windows deterministically. Returns `WindowRect` (`.as_tuple()` / `.to_dict()`); `gap` insets tiles; cross-platform and fully headless-testable; composes with any window-move backend.

### Locate UI Elements by Edge / Contour (No Template)

Find the clickable boxes on a screen you have never seen. Full reference: [`docs/source/Eng/doc/new_features/v132_features_doc.rst`](docs/source/Eng/doc/new_features/v132_features_doc.rst).

- **`find_shapes` / `find_rectangles`** (`AC_find_shapes`, `AC_find_rectangles`): every other locator needs something to look *for* — a template, a colour, some text. These need nothing: Canny edge detection + contour extraction returns the bounding boxes (`{x,y,width,height,area,center,aspect}`, largest first) of the distinct shapes, so a script can enumerate cards / buttons / input fields structurally and click the Nth one. `find_rectangles` keeps only convex quads and adds an `aspect_range=(min,max)` w/h filter (`(1.5,8)` wide buttons). Injectable haystack → headless-testable.

### ORB Feature Matching (Rotation / Scale / Theme Robust)

Find a target even when it is rotated, rescaled or re-themed. Full reference: [`docs/source/Eng/doc/new_features/v131_features_doc.rst`](docs/source/Eng/doc/new_features/v131_features_doc.rst).

- **`feature_match`** (`AC_feature_match`): pixel template matching (`match_template` / `match_masked`) correlates pixels, so it breaks the moment the target is rotated, scaled by an unlisted factor, or re-coloured (light/dark theme, hover). This matches ORB *keypoints* and fits a RANSAC homography, returning the four projected `corners`, the `center`, the `inliers` count and an inlier-fraction `score`. ORB border/patch sizes auto-scale down for icon-sized templates (OpenCV's defaults reject them). Core OpenCV only (no contrib); injectable haystack → headless-testable.

### Structural-Similarity (SSIM) Comparison

Perceptual screen comparison that tells you *what* changed. Full reference: [`docs/source/Eng/doc/new_features/v130_features_doc.rst`](docs/source/Eng/doc/new_features/v130_features_doc.rst).

- **`ssim_compare` / `ssim_changed_regions`** (`AC_ssim_compare`, `AC_ssim_changed_regions`): pixel diff (`diff_screenshots`) fires on a one-pixel shift; a histogram (`detect_drift`) is blind to layout. SSIM is the standard visual-regression metric — tolerant of small illumination changes, sensitive to structural change. `ssim_compare` returns a 0..1 score (1.0 = identical); `ssim_changed_regions` returns boxes of what moved. `ignore=[[x,y,w,h]]` masks live clocks / cursors. Pure NumPy + OpenCV (no scikit-image); injectable image pair → headless-testable.

### Masked Template Matching

Match icons regardless of their background. Full reference: [`docs/source/Eng/doc/new_features/v129_features_doc.rst`](docs/source/Eng/doc/new_features/v129_features_doc.rst).

- **`match_masked` / `match_masked_all`** (`AC_match_masked`, `AC_match_masked_all`): plain template matching scores *every* pixel, so an icon clipped from one background fails over a different one. These count only the pixels you mark relevant — an explicit grayscale `mask`, or an RGBA template's alpha channel — so transparent / "don't care" pixels stop dragging the score down. Returns the same `Match` (score/center) as scored template matching; OpenCV masked `TM_CCORR_NORMED`, NaNs zeroed. Injectable haystack → headless-testable.

### Locate On-Screen Regions by Colour

Find the green status pill / red banner by colour. Full reference: [`docs/source/Eng/doc/new_features/v128_features_doc.rst`](docs/source/Eng/doc/new_features/v128_features_doc.rst).

- **`find_color_region` / `find_color_regions`** (`AC_find_color_region`): `color_stats` only describes a region's colour and `assert_pixel` checks one point — neither *locates* a coloured region. This masks pixels within `tolerance` of a target RGB and returns the connected blobs' boxes (`{x,y,width,height,area,center}`, largest first) — for status lights, progress fills, error banners where a template is brittle. Injectable haystack → headless-testable; OpenCV/NumPy via `je_open_cv`.

### Confidence-Returning Template Matching

Template matching that returns the score, searches multiple scales, and finds all occurrences. Full reference: [`docs/source/Eng/doc/new_features/v127_features_doc.rst`](docs/source/Eng/doc/new_features/v127_features_doc.rst).

- **`match_template` / `match_template_all` / `best_matches` / `TemplateMatch`** (`AC_match_template`, `AC_match_template_all`): the existing matcher (`find_object`) is single-scale and *discards the score*. This returns a `Match` with `score`/`scale`/`center`, searches `scales` for DPI/zoom tolerance, and enumerates every occurrence with non-maximum suppression. Injectable `haystack` (ndarray/path/PIL) → headless-testable on synthetic arrays; OpenCV/NumPy via the `je_open_cv` dependency.

### Wait for Window Title (Regex)

Block until a window title matches a regex (or vanishes). Full reference: [`docs/source/Eng/doc/new_features/v126_features_doc.rst`](docs/source/Eng/doc/new_features/v126_features_doc.rst).

- **`wait_until_window_title`** (`AC_wait_window_title`): `wait_for_window` matches a title substring and only waits for *appear*; `wait_until_window_closed` is substring vanish. This matches a regular expression by default (`regex=False` for substring) and can wait for the title to vanish (`present=False`) — e.g. wait for a tab to navigate to `r".*— Checkout$"`. Injectable title source, headless-testable.

### Grid / Table Cell Addressing

Address a table cell by (row, column) from cell bounding boxes. Full reference: [`docs/source/Eng/doc/new_features/v125_features_doc.rst`](docs/source/Eng/doc/new_features/v125_features_doc.rst).

- **`cluster_grid` / `locate_cell`** (`AC_grid_cell`): `anchor_locator` does pairwise relations but nothing addresses a 2-D grid. Given the cell bounding boxes (from `locate_all_image` / `find_text_matches`), this clusters them into rows (by centre-y within `row_tolerance`) and columns (by centre-x) and returns the centre of the 0-based `(row, col)` cell — ready to click. Pure clustering, fully headless-testable.

### Anchor Ordinal & Locate-All

Pick the Nth anchor-relative match, or enumerate them all. Full reference: [`docs/source/Eng/doc/new_features/v124_features_doc.rst`](docs/source/Eng/doc/new_features/v124_features_doc.rst).

- **`anchor_locate(..., ordinal=N)` / `anchor_locate_all`** (`AC_anchor_locate` ordinal, `AC_anchor_locate_all`): `anchor_locate` always returned the single nearest match — no way to grab "the 2nd row below the header" or list every row. Adds a 1-based `ordinal` selector (backward-compatible; `ordinal=1` = nearest) and `anchor_locate_all` returning every match sorted by distance — the building block for table/list-row selection. Pure ranking core, deterministic.

### Held Modifiers Across an Action Group

Hold ctrl/shift down across several actions, released even on error. Full reference: [`docs/source/Eng/doc/new_features/v123_features_doc.rst`](docs/source/Eng/doc/new_features/v123_features_doc.rst).

- **`hold_modifiers` / `plan_with_modifiers`** (`AC_with_modifiers`): `hotkey` releases its keys immediately — there was no way to hold a modifier down across several independent actions (shift-click range select, ctrl-click multi-select) with a guaranteed release. `hold_modifiers` is a context manager that presses on enter and releases in reverse on exit (in a `finally`, so nothing leaks); `plan_with_modifiers` is the pure plan. Injectable sink, deterministic.

### Unicode Text Entry (Emoji / CJK)

Type any Unicode (emoji / CJK / accented) that `write` can't. Full reference: [`docs/source/Eng/doc/new_features/v122_features_doc.rst`](docs/source/Eng/doc/new_features/v122_features_doc.rst).

- **`type_unicode` / `plan_paste` / `unicode_code_units`** (`AC_type_unicode`): `write` types through the virtual-key table and *raises* on emoji/CJK/many accented chars. `type_unicode` enters any text reliably by setting the clipboard and pasting (`modifier` ctrl/command). `unicode_code_units` splits text into UTF-16 code units (surrogate pairs) for KEYEVENTF_UNICODE backends. Pure-planning + injectable sink, deterministic.

### Wait for Region Colour

Block until a colour fills (or leaves) a screen region. Full reference: [`docs/source/Eng/doc/new_features/v121_features_doc.rst`](docs/source/Eng/doc/new_features/v121_features_doc.rst).

- **`wait_until_color`** (`AC_wait_color`): `wait_for_pixel` matches one point exactly and `wait_until_pixel_changes` detects any change at one point — neither waits for "the status light turns green" / "the progress bar fills" / "the red banner is gone". This counts pixels within `tolerance` of `target_rgb` over a region and succeeds when that fraction crosses `min_fraction` (or drops below it, `present=False`). Injectable sampler, headless-testable. Pure-stdlib.

### Relative Mouse Movement

Nudge the pointer by a delta from where it is. Full reference: [`docs/source/Eng/doc/new_features/v120_features_doc.rst`](docs/source/Eng/doc/new_features/v120_features_doc.rst).

- **`move_mouse_relative` / `relative_target`** (`AC_move_mouse_relative`): the mouse wrapper only had absolute `set_mouse_position` — no `moveRel(dx, dy)` for relative-pointer / canvas / FPS apps and incremental drags. Reads the live position and moves by the delta; `relative_target` is the pure arithmetic, and the getter/setter are injectable for headless tests. Pure-stdlib, deterministic.

### Hold Key / Auto-Repeat

Hold a key for a duration, or auto-repeat it at a fixed rate. Full reference: [`docs/source/Eng/doc/new_features/v119_features_doc.rst`](docs/source/Eng/doc/new_features/v119_features_doc.rst).

- **`hold_key` / `plan_key_hold`** (`AC_hold_key`): `type_keyboard` is an instant down+up — there was no "hold this key for N seconds" (game movement, hold-to-scroll) or "send it at R presses/second" (auto-repeat). `plan_key_hold` builds the deterministic op-plan (press/wait/release, or N spaced key events for `rate_hz`); `hold_key` routes waits to an injectable `sleep` and keys to an injectable `sink`. Pure-planning, deterministic.

### Wait Until Gone (Blocking Vanish Waits)

Block until a spinner / toast / dialog disappears. Full reference: [`docs/source/Eng/doc/new_features/v118_features_doc.rst`](docs/source/Eng/doc/new_features/v118_features_doc.rst).

- **`wait_until_gone` / `wait_until_image_gone` / `wait_until_text_gone`** (`AC_wait_image_gone`, `AC_wait_text_gone`): `wait_for_image`/`wait_for_text` only block until something *appears*, and `observer` fires async callbacks on vanish — there was no *blocking* "wait until this image/text disappears then continue" call. The generic `wait_until_gone` takes any predicate (headless-testable); the image/text helpers build it from the locate functions. `gone_for_s` debounces flicker. Returns a `WaitOutcome`. Pure-stdlib.

### Clear-Then-Type Field Entry

Reliably set a text field's value (the Playwright `fill` idiom). Full reference: [`docs/source/Eng/doc/new_features/v117_features_doc.rst`](docs/source/Eng/doc/new_features/v117_features_doc.rst).

- **`set_field_text` / `plan_field_set`** (`AC_set_field_text`): there was no single "focus → clear → set value" primitive, and `write` raises on emoji/CJK. This clears the field (select-all + delete) then enters the text — optionally via the clipboard (`paste=True`) which is the Unicode-safe path `write` can't do. `modifier` is the platform command key (`ctrl`/`command`). Pure-planning + injectable sink, deterministic.

## What's new (2026-06-22)

### Multi-Waypoint Mouse Gestures

Move or drag the pointer through a polyline of waypoints. Full reference: [`docs/source/Eng/doc/new_features/v116_features_doc.rst`](docs/source/Eng/doc/new_features/v116_features_doc.rst).

- **`plan_path` / `move_along_path` / `drag_path` / `path_easings`** (`AC_move_along_path`, `AC_drag_path`): `humanize` and `tween_drag` only interpolate a single start→end hop — there was no way to drive an arbitrary chain of waypoints (signatures, marquee selects, multi-stop drags) with the button held across the whole path. `plan_path` is pure eased point math (reusing `tween_drag`'s easings, junctions de-duplicated); the move/drag dispatch through an injectable sink for headless testing. Pure-stdlib, deterministic.

### Check-Digit Algorithms

Compute / verify Luhn, Verhoeff, Damm and ISO 7064 MOD 97-10 check digits. Full reference: [`docs/source/Eng/doc/new_features/v115_features_doc.rst`](docs/source/Eng/doc/new_features/v115_features_doc.rst).

- **`luhn_validate` / `luhn_check_digit` / `verhoeff_*` / `damm_*` / `mod97_10_*`** (`AC_checksum_validate`, `AC_checksum_digit`): `pii_text` detects card/IBAN shapes by regex and `data_quality` does regex validation, but nothing computed or verified a *check digit*. This adds the four schemes behind most identifiers (cards/IMEI, national IDs, IBAN) — the shared engine `identifier_validate` builds on. Pure-stdlib, deterministic.

### GNU gettext Catalog I/O (.po / .mo)

Read/compile the de-facto translation format. Full reference: [`docs/source/Eng/doc/new_features/v114_features_doc.rst`](docs/source/Eng/doc/new_features/v114_features_doc.rst).

- **`parse_po` / `read_mo` / `GettextCatalog` / `parse_po_file` / `read_mo_file`** (`AC_gettext_translate`, `AC_gettext_ngettext`): the repo pseudo-localises and renders ICU messages but couldn't read GNU gettext `.po`/`.mo`. This parses `.po` (contexts, plurals, the `Plural-Forms` header via `gettext.c2py`), compiles a standards-compliant `.mo` that Python's own `gettext.GNUTranslations` loads, and exposes `gettext`/`ngettext`/`pgettext`. Pure-stdlib, deterministic.

### ICU-lite MessageFormat (Plural / Select)

Render count-aware localised messages. Full reference: [`docs/source/Eng/doc/new_features/v113_features_doc.rst`](docs/source/Eng/doc/new_features/v113_features_doc.rst).

- **`format_message` / `plural_category` / `ordinal_category`** (`AC_format_message`): `i18n_test.check_catalog` only compares placeholder sets and `interpolate` is flat `${var}` — neither renders `"{count, plural, one {# item} other {# items}}"`. This implements the ICU MessageFormat subset most apps use: `select`, `plural`, `selectordinal` with CLDR categories, exact `=N` selectors, the `#` count, `offset:`, nesting and apostrophe quoting. Injectable plural rules. Pure-stdlib, deterministic.

### Locale-Aware List Formatting

Join items the way a language expects ("A, B, and C"). Full reference: [`docs/source/Eng/doc/new_features/v112_features_doc.rst`](docs/source/Eng/doc/new_features/v112_features_doc.rst).

- **`format_list`** (`AC_format_list`): a naive `", ".join` gives "A, B, C" with no "and"/"or" and no localisation. This implements the CLDR list-pattern composition with conjunction / disjunction / unit styles and per-locale conjunction words + serial-comma rule (`en`/`es`/`fr`/`de`/`pt`) — `format_list(["a","b","c"])` → "a, b, and c", `locale="es"` → "a, b y c". Pure-stdlib, deterministic.

### Bidirectional-Text QA (Trojan-Source Scan)

Catch invisible Unicode directional formatting (RTL QA + Trojan-source). Full reference: [`docs/source/Eng/doc/new_features/v111_features_doc.rst`](docs/source/Eng/doc/new_features/v111_features_doc.rst).

- **`detect_bidi_issues` / `bidi_controls` / `is_bidi_balanced` / `base_direction` / `is_trojan_source` / `strip_bidi_controls` / `has_bidi_controls`** (`AC_bidi_check`, `AC_bidi_strip`): `confusables` catches lookalike characters, but bidi controls (LRO/RLO/PDF, isolates, marks) can silently reorder rendered text — an RTL-QA gap and the "Trojan Source" attack (CVE-2021-42574). This lists the controls, checks nesting balance, infers base direction, and flags reordering formatting. Pure-stdlib (`unicodedata`), deterministic.

### Readability Scoring

Score how hard text is to read; gate generated copy on a reading grade. Full reference: [`docs/source/Eng/doc/new_features/v110_features_doc.rst`](docs/source/Eng/doc/new_features/v110_features_doc.rst).

- **`flesch_reading_ease` / `flesch_kincaid_grade` / `gunning_fog` / `smog_index` / `automated_readability_index` / `readability_report` / `readability_stats` / `count_syllables`** (`AC_readability_report`): the text utilities canonicalise, match and rank text but never scored *difficulty*. This adds the classic English readability formulae over a deterministic tokeniser and syllable heuristic, so a test can assert an on-screen message or label stays within a target reading grade. Pure-stdlib (`re`/`math`), deterministic.

### Confusable / Homoglyph Detection

Catch Unicode visual spoofing (IDN-homograph phishing, lookalike labels). Full reference: [`docs/source/Eng/doc/new_features/v109_features_doc.rst`](docs/source/Eng/doc/new_features/v109_features_doc.rst).

- **`confusable_skeleton` / `is_confusable` / `detect_homoglyphs` / `is_mixed_script` / `scripts_of`** (`AC_confusable_scan`, `AC_confusable_compare`): a Cyrillic `"а"` is pixel-for-pixel a Latin `"a"`, so `"pаypal"` reads as `"paypal"` yet compares unequal. Following Unicode TR39, this folds confusables to a prototype skeleton (strings match when skeletons match) and flags mixed-script tokens. Pure-stdlib (`unicodedata`), deterministic.

### Locale-Aware String Collation

Sort strings the way a reader of the language expects. Full reference: [`docs/source/Eng/doc/new_features/v108_features_doc.rst`](docs/source/Eng/doc/new_features/v108_features_doc.rst).

- **`sort_strings` / `collation_compare` / `collation_key`** (`AC_collation_sort`, `AC_collation_compare`): Python's default `sorted` is codepoint order, so `"Z" < "a"` and `"ä"` lands far from `"a"`. This Unicode-Collation-lite key orders by base letter, then accent (secondary), then case (tertiary), with an optional `tailoring` alphabet so Swedish puts `å ä ö` after `z`. Pure-stdlib (`unicodedata`), deterministic across platforms — unlike `locale.strxfrm`.

### Transactional Outbox

Durably buffer events and drain them at-least-once. Full reference: [`docs/source/Eng/doc/new_features/v107_features_doc.rst`](docs/source/Eng/doc/new_features/v107_features_doc.rst).

- **`Outbox`** (`AC_outbox_enqueue`, `AC_outbox_pending`): `events.cloud_events` posts synchronously with no durability — a crash or network blip loses the event. The outbox persists each event first, then `drain`s pending entries through an injected sink with at-least-once delivery: a sink failure leaves the entry pending for retry until `max_attempts`, after which it is dead-lettered. `save` / `load` keep events across restarts. Pure-stdlib, deterministic.

### Optimistic-Concurrency Versioned Store

Update only if the version is unchanged (compare-and-swap / If-Match). Full reference: [`docs/source/Eng/doc/new_features/v106_features_doc.rst`](docs/source/Eng/doc/new_features/v106_features_doc.rst).

- **`VersionedStore` / `VersionConflict` / `if_match_header` / `check_if_match`** (`AC_cas_put`, `AC_cas_get`): `http_conditional` used ETag for read caching but never for write concurrency. This local compare-and-swap store `put`s only when `expected_version` matches (raising `VersionConflict` on a stale write), bumps a monotonic version, and bridges to HTTP `If-Match` — the write side of the ETag story. Pure-stdlib, deterministic.

### Per-Stream Sequence-Gap Detection

Detect missing / out-of-order / duplicate messages by sequence number. Full reference: [`docs/source/Eng/doc/new_features/v105_features_doc.rst`](docs/source/Eng/doc/new_features/v105_features_doc.rst).

- **`SequenceTracker`** (`AC_sequence_observe`): nothing tracked per-stream monotonic sequence numbers. `observe(stream, seq)` classifies each as `ok` / `duplicate` / `gap` (with the `missing` numbers) / `reorder` (late arrivals fill gaps), and exposes `gaps` and `high_water`. Complements `dedup_window`. Pure-stdlib, deterministic.

### Time-Windowed Deduplication

Drop duplicate/redelivered messages within a TTL window. Full reference: [`docs/source/Eng/doc/new_features/v104_features_doc.rst`](docs/source/Eng/doc/new_features/v104_features_doc.rst).

- **`DedupWindow`** (`AC_dedup_check`): `work_queue` dedups only in-flight references, so a completed reference re-enqueues and redelivered webhooks reprocess. This sliding-window inbox `check_and_mark`s a message id — `True` the first time, `False` for a duplicate within `ttl_s` — converting at-least-once delivery to exactly-once-in-window. Injectable clock, bounded size. Pure-stdlib, deterministic.

### Idempotency-Key Store

Run a side effect once, replay its response on retries. Full reference: [`docs/source/Eng/doc/new_features/v103_features_doc.rst`](docs/source/Eng/doc/new_features/v103_features_doc.rst).

- **`IdempotencyStore` / `request_fingerprint` / `IdempotencyConflict`** (`AC_idempotency_begin`, `AC_idempotency_complete`): `RetryPolicy` re-executes and `work_queue` dedups only in-flight refs — nothing cached the first result. This Stripe-style store returns `new`/`in_progress`/`completed` for a key, replays the stored response, raises on a fingerprint conflict, and supports injectable-clock TTL + JSON persistence. Pure-stdlib, deterministic.

### Moving-Average Smoothing

Smooth a noisy value series. Full reference: [`docs/source/Eng/doc/new_features/v102_features_doc.rst`](docs/source/Eng/doc/new_features/v102_features_doc.rst).

- **`sma` / `wma` / `ewma` / `rolling`** (`AC_sma`, `AC_ewma`): `stats.describe` summarizes a whole sample and `timeseries` rolls counters into rates, but nothing smoothed a noisy signal. This adds trailing simple/weighted/exponentially-weighted moving averages and a generic rolling reducer, all returning a same-length list aligned to the input timeline. Pure-stdlib, deterministic.

### Single-Series Anomaly Detection

Flag the spike in one live metric series. Full reference: [`docs/source/Eng/doc/new_features/v101_features_doc.rst`](docs/source/Eng/doc/new_features/v101_features_doc.rst).

- **`detect_anomalies` / `mad_anomalies` / `zscore_anomalies` / `ewma_control`** (`AC_detect_anomalies`): `data_drift` is two-batch distribution shift and `slo.burn_alerts` only thresholds budget burn — neither points at *which* value in one series is anomalous. This flags outliers via robust MAD (modified z-score), plain z-score, and an EWMA control chart (with an optional in-control baseline) — `{index, value, score, is_anomaly}` records. Pure-stdlib, deterministic.

### Near-Duplicate Text Detection (SimHash / MinHash)

Fingerprint text to find near-dups at scale. Full reference: [`docs/source/Eng/doc/new_features/v100_features_doc.rst`](docs/source/Eng/doc/new_features/v100_features_doc.rst).

- **`simhash` / `near_duplicates` / `minhash_signature` / `minhash_similarity`** (`AC_simhash`, `AC_near_duplicates`): `fuzzy_dedupe` is O(n²) pairwise with no stable fingerprint and `image_dedup` only hashes pixels. This adds the text analog — SimHash (Hamming-distance near-dup clustering) and MinHash (estimated Jaccard) using a fixed `blake2b` hash for deterministic fingerprints. Pairs with `normalize_text`. Pure-stdlib.

### String-Distance Similarity Metrics

Match typos and reordered tokens. Full reference: [`docs/source/Eng/doc/new_features/v99_features_doc.rst`](docs/source/Eng/doc/new_features/v99_features_doc.rst).

- **`levenshtein` / `damerau_levenshtein` / `jaro` / `jaro_winkler` / `jaccard` / `dice` / `similarity`** (`AC_text_similarity`): `fuzzy` exposed only difflib's gestalt ratio. This adds the edit-distance and token-set metrics it lacks — Jaro-Winkler (standard for short labels), Damerau (transposition-aware), and char-n-gram Jaccard/Dice — plus a unified `similarity()` that normalizes every metric to `[0, 1]`. Pairs with `normalize_text`. Pure-stdlib, deterministic.

### Time-Series Transforms

Turn counters into rates; downsample and resample. Full reference: [`docs/source/Eng/doc/new_features/v98_features_doc.rst`](docs/source/Eng/doc/new_features/v98_features_doc.rst).

- **`ts_rate` / `ts_irate` / `ts_increase` / `ts_delta` / `ts_downsample` / `ts_resample`** (`AC_ts_rate`, `AC_ts_downsample`): `observability` counters store only the current value (no counter→rate anywhere) and `cost_telemetry` only buckets by day. This adds Prometheus-style reset-aware rate/increase/delta over `(timestamp, value)` series, tumbling-bucket downsampling (avg/sum/min/max/first/last/count), and grid resampling (last/linear/none). No wall clock — deterministic. Pure-stdlib.

### Unicode Text Normalisation & Slugify

Canonicalize text before fuzzy/search/OCR matching. Full reference: [`docs/source/Eng/doc/new_features/v97_features_doc.rst`](docs/source/Eng/doc/new_features/v97_features_doc.rst).

- **`normalize_text` / `deaccent` / `slugify` / `normalize_quotes` / `fold_whitespace`** (`AC_normalize_text`, `AC_slugify`): `fuzzy` and `search_index.tokenize` only lowercase and OCR matching only `.lower()`+substring, so `"Café"` (NFC) vs `"Café"` (NFD) vs `"cafe"` compare unequal. This adds the missing canonicalization layer (NFKC + casefold + whitespace fold, accent stripping, smart-quote mapping, ASCII slugs). Pure-stdlib (`unicodedata`), deterministic.

### JSON-Schema Compatibility Checking

Classify schema changes as backward/forward/full. Full reference: [`docs/source/Eng/doc/new_features/v96_features_doc.rst`](docs/source/Eng/doc/new_features/v96_features_doc.rst).

- **`check_compatibility` / `diff_schemas` / `is_backward_compatible` / `is_forward_compatible` / `is_full_compatible`** (`AC_check_compatibility`): we could validate against and generate JSON Schemas but couldn't answer "will an old consumer still read new data?". This classifies changes (added-required field, removed field, narrowed/widened type, enum add/remove) under Confluent/Avro backward/forward/full rules over the object subset. Pure-stdlib, deterministic.

### Typed Configuration Schema

Validate config into a typed object. Full reference: [`docs/source/Eng/doc/new_features/v95_features_doc.rst`](docs/source/Eng/doc/new_features/v95_features_doc.rst).

- **`ConfigSchema` / `ConfigField` / `validate_config` / `coerce`** (`AC_validate_config`): `assets._coerce` coerces one value and `json_schema` validates structure, but nothing bound a resolved config dict into a typed object with required-field enforcement and choice constraints. This coerces types (`str`/`int`/`float`/`bool`), applies defaults, enforces required/choices, and returns `{ok, config, errors}` — a stdlib pydantic-settings analog. Pure-stdlib, deterministic.

### OTLP/JSON Span Export

Export spans the way a collector ingests them. Full reference: [`docs/source/Eng/doc/new_features/v94_features_doc.rst`](docs/source/Eng/doc/new_features/v94_features_doc.rst).

- **`spans_to_otlp` / `attributes_to_otlp` / `write_otlp`** (`AC_spans_to_otlp`): `agent_trace.to_otel` returned flat dicts that aren't valid OTLP/JSON (no resourceSpans/scopeSpans nesting, times not as uint64 strings). This wraps spans in the proper envelope with hex IDs, uint64-string times, and OTLP `KeyValue` attribute encoding — what an OpenTelemetry collector's file exporter reads. Pairs with `trace_context`. Pure-stdlib, deterministic.

### Canonical Log Lines & Structured Logging

One wide event per run, with trace correlation. Full reference: [`docs/source/Eng/doc/new_features/v93_features_doc.rst`](docs/source/Eng/doc/new_features/v93_features_doc.rst).

- **`CanonicalLogLine` / `JSONLogFormatter` / `bind_trace_context`** (`AC_canonical_log`): `logging_instance` emits a fixed pipe-delimited string with no JSON and no trace/span fields. This adds a Stripe-style canonical log line (field accumulator + `timer` with injectable clock) and a JSON `logging.Formatter` that carries `trace_id`/`span_id` — the log-trace correlation counterpart to `trace_context`. Pure-stdlib, deterministic.

### Conditional HTTP Requests & Cache Validators

Skip re-downloading unchanged resources (ETag / 304). Full reference: [`docs/source/Eng/doc/new_features/v92_features_doc.rst`](docs/source/Eng/doc/new_features/v92_features_doc.rst).

- **`store_validators` / `conditioned_call` / `is_fresh` / `parse_cache_control` / `is_not_modified`** (`AC_parse_cache_control`, `AC_store_validators`): `http_request` never sent `If-None-Match`/`If-Modified-Since` nor read `Cache-Control`, so every poll re-downloaded. This extracts validators, parses `Cache-Control` (max-age/no-store/…), decides freshness by an explicit age, conditions the next request, and detects `304 Not Modified`. Pure-stdlib, deterministic.

### Cookie Jar (HTTP Session Carry)

Carry a session across HTTP calls. Full reference: [`docs/source/Eng/doc/new_features/v91_features_doc.rst`](docs/source/Eng/doc/new_features/v91_features_doc.rst).

- **`CookieJar` / `parse_set_cookie`** (`AC_cookie_header`, `AC_parse_set_cookie`): `http_request` is stateless — no session cookies persisted across calls, so a login-then-call flow couldn't carry a session headlessly. This parses `Set-Cookie` headers into a jar, builds the `Cookie` request header, and saves/loads the jar as JSON (cookies cleared on `Max-Age<=0`/empty). Pure-stdlib, deterministic.

### HTTP Content Negotiation & Decompression

Build `Accept` headers and decode gzip/deflate. Full reference: [`docs/source/Eng/doc/new_features/v90_features_doc.rst`](docs/source/Eng/doc/new_features/v90_features_doc.rst).

- **`build_accept` / `build_accept_encoding` / `parse_quality_values` / `decode_body` / `negotiated_call`** (`AC_decode_body`, `AC_parse_quality_values`): `urllib`/`http_request` never set `Accept-Encoding` nor decoded `Content-Encoding`, so compressed bodies arrived raw. This adds `Accept`/`Accept-Encoding` builders, a q-value parser (sorted by quality), and gzip/deflate (incl. raw deflate) decoding. Brotli excluded (not stdlib). Pure-stdlib, deterministic.

### multipart/form-data Build & Parse

Build file-upload bodies. Full reference: [`docs/source/Eng/doc/new_features/v89_features_doc.rst`](docs/source/Eng/doc/new_features/v89_features_doc.rst).

- **`build_multipart` / `parse_multipart` / `MultipartFile`** (`AC_build_multipart`, `AC_parse_multipart`): `http_request` sent only JSON/raw — there was no file upload, and stdlib `cgi` (which parsed multipart) was removed in 3.13. This assembles a `multipart/form-data` body from text fields and files with an injectable boundary (byte-stable), and parses one back into `{fields, files}`. Pure-stdlib, deterministic.

### Secret Redaction for Config & Logs

Mask secrets before logging or exporting. Full reference: [`docs/source/Eng/doc/new_features/v88_features_doc.rst`](docs/source/Eng/doc/new_features/v88_features_doc.rst).

- **`redact_config` / `redact_secret_text`** (`AC_redact_config`, `AC_redact_secret_text`): `utils/redaction` only blurs screenshots and `secrets_scan` only *detects* — neither returned a masked copy. This reuses the `secrets_scan` detector (key-name patterns, AWS/bearer formats, high-entropy) to return a redacted deep copy of a config structure, and to mask secret-looking tokens in a free-text log line (preserving surrounding words). Vault refs (`${secrets.*}`) are left intact. Pure-stdlib, deterministic.

### RFC 8288 Link Header & Pagination

Parse `Link` headers and follow `rel="next"`. Full reference: [`docs/source/Eng/doc/new_features/v87_features_doc.rst`](docs/source/Eng/doc/new_features/v87_features_doc.rst).

- **`parse_link_header` / `next_url` / `links_by_rel` / `paginate`** (`AC_parse_link_header`, `AC_next_url`): paginated REST APIs return `Link: <...>; rel="next"` but nothing parsed it. This parses the header (quoted values with commas, multiple links), indexes by relation, and `paginate` walks `rel="next"` over an injected `fetch` (transport/cassette) up to `max_pages`. Pure-stdlib, deterministic.

### Referential Integrity Checks

Foreign-key, unique, accepted-values and row-count checks across tables. Full reference: [`docs/source/Eng/doc/new_features/v86_features_doc.rst`](docs/source/Eng/doc/new_features/v86_features_doc.rst).

- **`check_foreign_key` / `check_unique_key` / `check_accepted_values` / `check_row_count`** (`AC_check_foreign_key`, `AC_check_unique_key`, `AC_check_accepted_values`, `AC_check_row_count`): `validate_rows` is intra-row, single-table (its `unique` only dedupes within one batch). This adds dbt-style generic checks — parent/child foreign keys across two tables, single/composite key uniqueness, accepted-values, and row-count bounds — over rows from `load_rows`/`query_sqlite`. Pure-stdlib, deterministic.

### URI-Scheme Value References

Store pointers, not secrets, in config. Full reference: [`docs/source/Eng/doc/new_features/v85_features_doc.rst`](docs/source/Eng/doc/new_features/v85_features_doc.rst).

- **`resolve_ref` / `resolve_refs_in` / `is_ref` / `RefResolver`** (`AC_resolve_ref`, `AC_resolve_refs`): `interpolate` hardcoded only `${secrets.NAME}` and `AssetStore` refs were vault-name-only — there was no general read-time indirection. This resolves `env://VAR`, `file://path` (with an optional `base_dir` traversal guard), and `secret://name` (injectable resolver or the governance broker), and walks nested structures resolving every reference. Env reader / secret resolver / base dir are injectable. Pure-stdlib, deterministic.

## What's new (2026-06-21)

### W3C Baggage Propagation

Carry cross-cutting key-value context across HTTP. Full reference: [`docs/source/Eng/doc/new_features/v84_features_doc.rst`](docs/source/Eng/doc/new_features/v84_features_doc.rst).

- **`Baggage` / `parse_baggage` / `format_baggage` / `inject_baggage` / `extract_baggage`** (`AC_baggage_parse`, `AC_baggage_format`): `trace_context` carried trace/span identity but nothing propagated cross-cutting context (`run_id`/`tenant`/`experiment`). This implements the W3C Baggage header — a percent-encoded `key=value` list — with an immutable `Baggage` (set/remove return new instances) and case-insensitive inject/extract over a headers dict. Pairs with `trace_context`. Pure-stdlib, deterministic.

### Dataset Diff (Row-Set Change Report)

Diff two tabular extracts by key. Full reference: [`docs/source/Eng/doc/new_features/v83_features_doc.rst`](docs/source/Eng/doc/new_features/v83_features_doc.rst).

- **`diff_rows` / `cell_changes` / `summarize_diff`** (`AC_diff_rows`, `AC_cell_changes`): the framework diffed screens/snapshots but had nothing to diff two **tabular** row-sets by key. This keys both sides and reports `{added, removed, changed, unchanged}` (changed carries `{key, old, new}`), expands per-cell `{key, column, old, new}` changes, and counts each bucket. Supports composite keys; last-write-wins on duplicates. Pure-stdlib, deterministic.

### Distribution Drift Detection

Check whether today's data is shaped like the baseline. Full reference: [`docs/source/Eng/doc/new_features/v82_features_doc.rst`](docs/source/Eng/doc/new_features/v82_features_doc.rst).

- **`psi` / `ks_two_sample` / `categorical_drift` / `detect_drift`** (`AC_detect_drift`, `AC_categorical_drift`): `stats` had A/B experiment tests but no Population Stability Index and no KS two-sample test for reference-vs-current distributions. This adds PSI (quantile-binned log-ratio), the KS statistic with a Kolmogorov p-value, and a categorical chi-square + total-variation summary — pairing with `data_profile`. `detect_drift` gives a one-call `{psi, drifted, ks}` verdict. Pure-stdlib, deterministic.

### Layered Configuration Resolver

Compose config with `defaults < file < env < CLI` precedence. Full reference: [`docs/source/Eng/doc/new_features/v81_features_doc.rst`](docs/source/Eng/doc/new_features/v81_features_doc.rst).

- **`LayeredConfig` / `deep_merge` / `SourceTrace`** (`AC_resolve_config`, `AC_explain_config`): `json_patch.merge_patch` merges two docs, `config_sync` is last-write-wins, `AssetStore` is flat-per-env — none compose an ordered precedence stack with deep merge or report which layer won each key. `add_layer(name, mapping, priority)` then `resolve()` deep-merges (nested dicts recursively, scalars/lists replaced); `explain("db.host")` names the winning layer. Layers are caller-supplied (env passed in, never `os.environ` implicitly). Pure-stdlib, deterministic.

### Server-Sent Events (SSE) Client Parser

Consume `text/event-stream` responses. Full reference: [`docs/source/Eng/doc/new_features/v80_features_doc.rst`](docs/source/Eng/doc/new_features/v80_features_doc.rst).

- **`parse_event_stream` / `SSEParser` / `SSEEvent`** (`AC_parse_sse`): the MCP HTTP transport emits SSE, but nothing consumed it — a streaming LLM/agent/chatops endpoint left `http_request` with a raw blob. This implements the WHATWG event-stream parsing algorithm (`event`/`data`/`id`/`retry`, comments, the leading-space rule, blank-line dispatch) with an incremental `feed` for chunks and a one-shot `parse_event_stream`. Pure-stdlib, fully deterministic.

### Dotenv (.env) Parsing

Read 12-factor `.env` files into config. Full reference: [`docs/source/Eng/doc/new_features/v79_features_doc.rst`](docs/source/Eng/doc/new_features/v79_features_doc.rst).

- **`parse_dotenv` / `load_dotenv` / `dotenv_values` / `dump_dotenv`** (`AC_parse_dotenv`, `AC_load_dotenv`): `load_vars_from_json` ingested flat JSON but nothing read the de-facto `.env` file. This parses `KEY=VALUE` lines (`export` prefixes, single/double quoting, `\n`/`\t` escapes, inline comments) into a plain dict — no `python-dotenv` dependency. The loader merges into a caller-supplied mapping rather than mutating `os.environ`, so it stays safe and deterministic. Pure-stdlib.

### RFC 9457 Problem Details Parsing

Read standardized API errors out of HTTP responses. Full reference: [`docs/source/Eng/doc/new_features/v78_features_doc.rst`](docs/source/Eng/doc/new_features/v78_features_doc.rst).

- **`parse_problem` / `is_problem` / `raise_for_problem` / `ProblemDetails`** (`AC_parse_problem`): `http_request` returned a non-2xx body unparsed, so flows and `assert_http` had no structured way to read a standardized API error. This parses the RFC 9457 `application/problem+json` document — registered `type`/`title`/`status`/`detail`/`instance` members plus vendor extensions — returning `None` for non-problem responses or raising `HttpProblemError`. Pure-stdlib, fully deterministic.

### Data Profiling & Schema Inference

Survey a row-set and propose a validation schema. Full reference: [`docs/source/Eng/doc/new_features/v77_features_doc.rst`](docs/source/Eng/doc/new_features/v77_features_doc.rst).

- **`profile_rows` / `infer_schema`** (`AC_profile_rows`, `AC_infer_schema`): `validate_rows` consumes a hand-written schema and `stats.describe` summarizes one numeric list — nothing surveyed a whole row-set. This profiles each column (null fraction, cardinality, inferred type, top values, numeric min/max/mean) and infers a `validate_rows`-compatible schema (required where non-null, unique where distinct, numeric bounds) — the profiler step that feeds the existing validator. Pure-stdlib, fully deterministic.

### W3C Trace Context Propagation

Correlate spans and logs across HTTP boundaries. Full reference: [`docs/source/Eng/doc/new_features/v76_features_doc.rst`](docs/source/Eng/doc/new_features/v76_features_doc.rst).

- **`SpanContext` / `new_root_context` / `child_context` / `inject_context` / `extract_context`** (`AC_trace_inject`, `AC_trace_extract`): the existing tracer and `agent_trace` spans carried no IDs, so a span on one side of an HTTP call couldn't be correlated with the work it triggered on the other. This implements the W3C Trace Context standard — generate/parse/propagate `traceparent` + `tracestate` headers (version-`00`, rejects malformed/all-zero IDs), with an injectable RNG for deterministic IDs in tests. Pure-stdlib.

### HTTP Record & Replay Cassette

Re-run API flows in CI with no live server. Full reference: [`docs/source/Eng/doc/new_features/v75_features_doc.rst`](docs/source/Eng/doc/new_features/v75_features_doc.rst).

- **`Cassette` / `CassetteMissError`** (`AC_http_replay`): the HTTP client hardcoded its `urllib` transport, so a flow driving a real API couldn't be re-run offline. The client now exposes a `build_call` / `urllib_transport` seam, and this adds a VCR-style cassette — `replay` returns a recorded response for a matching request (pure, no network — the CI-valuable half), `recording_transport` is a thin pass-through over the live transport. Match on `method`/`url` (optionally `body`); `save`/`load` JSON cassettes. Pure-stdlib.

### Bulkhead & Rate-Limit Headers

Cap concurrency, honor server back-off. Full reference: [`docs/source/Eng/doc/new_features/v74_features_doc.rst`](docs/source/Eng/doc/new_features/v74_features_doc.rst).

- **`Bulkhead` / `next_delay` / `parse_retry_after` / `parse_ratelimit`** (`AC_bulkhead_run`, `AC_retry_after`): `resilience` recovers and `rate_limit` paces, but nothing capped *simultaneous* in-flight calls (a slow dependency could exhaust every worker) and the HTTP client ignored `Retry-After`/`RateLimit-*`. This adds a bulkhead (bounded-concurrency permit that sheds load with `BulkheadFullError` when full) and parsers for the server's advised delay (delta-seconds or HTTP-date). Non-blocking permit counting → deterministic, no threads in tests. Pure-stdlib.

### Streaming Latency Percentiles

Mergeable p99 for load/soak runs. Full reference: [`docs/source/Eng/doc/new_features/v73_features_doc.rst`](docs/source/Eng/doc/new_features/v73_features_doc.rst).

- **`LatencyDigest` / `exact_percentiles`** (`AC_percentiles`): `stats.percentile` needs the full sorted list; this adds a HdrHistogram-style digest with O(1) `record`, bounded memory (significant-figure buckets), and `merge` for cross-shard aggregation — the property you need for a correct aggregate p99 from per-worker results. `exact_percentiles` covers the small-set case (arbitrary quantiles). Pure-stdlib `math`.

### Service-Level Objectives (SLO)

SLI, error budget and burn-rate alerts. Full reference: [`docs/source/Eng/doc/new_features/v72_features_doc.rst`](docs/source/Eng/doc/new_features/v72_features_doc.rst).

- **`evaluate_slo` / `burn_rate` / `burn_alerts` / `default_burn_rules`** (`AC_evaluate_slo`, `AC_burn_alerts`): the framework emitted raw signals but had no SLO layer. This computes the SLI over outcome records (`[{timestamp, ok}]`), the error budget against a target, and the **multi-window multi-burn-rate** alerts from the Google SRE workbook (page 14.4×@1h, 6×@6h; ticket 1×@3d — firing only when both windows exceed the threshold). Records are plain data, clock injectable, fully deterministic. Pure-stdlib.

### Chaos Experiments

Inject faults, verify the system holds. Full reference: [`docs/source/Eng/doc/new_features/v71_features_doc.rst`](docs/source/Eng/doc/new_features/v71_features_doc.rst).

- **`ChaosExperiment` / `run_experiment` / `Probe` / `latency_fault` / `exception_fault`** (`AC_run_chaos`): `resilience` *recovers* from failures; this *causes* them and checks a steady-state hypothesis still holds (Chaos Toolkit lifecycle — verify before, inject faults, verify after, roll back LIFO). Probes/faults/rollbacks are callables; the clock/RNG/sleep are injectable so experiments run **deterministically** in tests with no real failures or sleeping. `AC_run_chaos` drives an action-list spec. Pure-stdlib.

### JSON Contract & Snapshot Matching

Match, diff and snapshot JSON payloads. Full reference: [`docs/source/Eng/doc/new_features/v70_features_doc.rst`](docs/source/Eng/doc/new_features/v70_features_doc.rst).

- **`match_json` / `diff_json` / `normalize_json` / `snapshot_json`** (`AC_match_json`, `AC_diff_json`): `json_schema` validates against an authored schema and `jsonpath` extracts, but nothing matched two payloads with relaxed rules or diffed them path-by-path. This adds contract/snapshot matching — `partial` (subset), `match_type` (Pact-style `like`), `ignore` volatile paths — returning `{path, kind}` mismatches (`missing`/`extra`/`changed`), plus golden-master `snapshot_json`. Composes with `json_schema` + `json_patch`; pure-stdlib.

### SLSA Build Provenance

Attest what was built. Full reference: [`docs/source/Eng/doc/new_features/v69_features_doc.rst`](docs/source/Eng/doc/new_features/v69_features_doc.rst).

- **`build_provenance` / `subject_for` / `verify_provenance` / `write_provenance`** (`AC_build_provenance`, `AC_verify_provenance`): the framework signs action files and inventories deps (SBOM) but couldn't attest *what was produced by which build*. This adds an in-toto v1 Statement with a SLSA v1 provenance predicate over file `sha256` digests, and a verifier that re-hashes the artifacts (tamper → mismatch). Complements `action_signing` + `sbom`; pure-stdlib `hashlib`+`json`, fully offline.

### Feature Flags

Toggle behavior with targeting & rollout. Full reference: [`docs/source/Eng/doc/new_features/v68_features_doc.rst`](docs/source/Eng/doc/new_features/v68_features_doc.rst).

- **`FlagStore` / `evaluate_flag` / `is_enabled` / `assign_variant`** (`AC_evaluate_flag`, `AC_flag_enabled`): `decision_table` is one-shot DMN and `ab_locator` is locator A/B — neither is a product flag store with sticky % rollout. This adds an OpenFeature-shaped engine: targeting rules (`eq`/`in`/`semver_*`…), weighted variants, kill switch, and consistent-hash bucketing (`sha256(key.salt.context_key)`) so a subject is **sticky**. Returns `{value, variant, reason}` (`TARGETING_MATCH`/`SPLIT`/`DISABLED`/`ERROR`). Pure-stdlib, deterministic.

### Text Diff, Patch & Three-Way Merge

Apply and merge text diffs. Full reference: [`docs/source/Eng/doc/new_features/v67_features_doc.rst`](docs/source/Eng/doc/new_features/v67_features_doc.rst).

- **`unified_diff` / `apply_unified` / `three_way_merge`** (`AC_unified_diff`, `AC_apply_unified`, `AC_three_way_merge`): `difflib` *generates* a unified diff but the stdlib can't *apply* one, and there was no three-way merge. This adds the missing applier (walks `@@` hunks, verifies context, raises on mismatch) and a line-based three-way merge (non-overlapping edits combine cleanly; overlapping ones emit `<<<<<<<` conflict markers). Complements `json_patch` (structured JSON); pure-stdlib `difflib`.

### Calendar Recurrence Rules (RRULE)

Schedule "every 2nd Tuesday". Full reference: [`docs/source/Eng/doc/new_features/v66_features_doc.rst`](docs/source/Eng/doc/new_features/v66_features_doc.rst).

- **`parse_rrule` / `occurrences` / `next_occurrence`** (`AC_rrule_occurrences`, `AC_rrule_next`): the scheduler's cron is 5-field interval-only — it can't express "every 2nd Tuesday", "the last weekday of the month", or "every weekday for 10 occurrences". This adds an RFC 5545 (iCalendar) RRULE parser + occurrence expander supporting `FREQ`/`INTERVAL`/`COUNT`/`UNTIL`/`BYDAY` (with ordinals like `2MO`/`-1FR`)/`BYMONTHDAY`/`BYMONTH`/`BYSETPOS`/`WKST`. Pure-stdlib `datetime`+`calendar`, injectable clock for deterministic `next_occurrence`.

### Statistics & A/B Significance

Decide whether a difference is real. Full reference: [`docs/source/Eng/doc/new_features/v65_features_doc.rst`](docs/source/Eng/doc/new_features/v65_features_doc.rst).

- **`describe` / `percentile` / `two_proportion_z_test` / `welch_t_test` / `cohens_d` / `chi_square_2x2`** (`AC_describe_stats`, `AC_ab_significance`): `ab_locator` ranks by raw success rate and `run_history` stores durations, but nothing computed percentiles or significance. This adds the analysis layer — summary stats + p50/p90/p95/p99, a two-proportion z-test (with CI), Welch's t-test (exact t-distribution p-value via the incomplete beta — no SciPy), Cohen's d, and a 2×2 chi-square. The normal CDF is exact via `math.erf`; validated against textbook values (incl. the chi²=z² identity). Pure-stdlib `math`+`statistics`.

### Full-Text Search (BM25)

Rank a document corpus by relevance. Full reference: [`docs/source/Eng/doc/new_features/v64_features_doc.rst`](docs/source/Eng/doc/new_features/v64_features_doc.rst).

- **`SearchIndex` / `search_documents` / `tokenize`** (`AC_search_documents`, `ac_search_documents`): `fuzzy` is pairwise and `skill_library` matches substrings alphabetically — neither ranks a corpus by relevance. This adds an inverted-index search ranked with Okapi BM25 (`k1=1.5`, `b=0.75`, `IDF = ln(1+(N−df+0.5)/(df+0.5))`) or TF-IDF, so a rare term out-ranks a common one, term frequency saturates, and long docs are normalized down. Incremental `add`/`remove`, optional stop-words, deterministic ranking. Pure-stdlib `math`+`collections`+`re` — no database.

### JSON Pointer, Patch & Merge Patch

Address, diff and patch JSON. Full reference: [`docs/source/Eng/doc/new_features/v63_features_doc.rst`](docs/source/Eng/doc/new_features/v63_features_doc.rst).

- **`resolve_pointer` / `make_patch` / `apply_patch` / `merge_patch` / `make_merge_patch`** (`AC_resolve_pointer`, `AC_apply_json_patch`, `AC_make_json_patch`, `AC_merge_patch`): `jsonpath` is read-only and `approval` compares whole artifacts — nothing could address one location, compute a structured delta, or apply a partial update. This adds the three IETF primitives — JSON Pointer (RFC 6901), JSON Patch (RFC 6902, all six ops, **atomic** apply), and JSON Merge Patch (RFC 7386, `null` deletes) — for config-drift detection, partial updates, HTTP PATCH bodies, and golden-master deltas. Pure-stdlib `json`+`copy`, validated against the RFC test vectors.

### Client-Side Rate Limiting

Stay under API quotas. Full reference: [`docs/source/Eng/doc/new_features/v62_features_doc.rst`](docs/source/Eng/doc/new_features/v62_features_doc.rst).

- **`TokenBucket` / `SlidingWindowLimiter` / `throttle`** (`AC_rate_limit`, `ac_rate_limit`): `RetryPolicy`/`CircuitBreaker` recover from failures but nothing shaped the *rate* of calls. This adds a token bucket (smooth rate + burst), a sliding-window limiter (Cloudflare's O(1) weighted counter), and a leading-edge throttle decorator. Every limiter takes an injectable `clock` (and `acquire` a `sleep`) so it's fully deterministic in CI with no real delays. `AC_rate_limit` gates an action against a named bucket, returning `{acquired, tokens, wait}`.

### JSON Web Tokens (JWT)

Mint and verify bearer tokens for the APIs you automate. Full reference: [`docs/source/Eng/doc/new_features/v61_features_doc.rst`](docs/source/Eng/doc/new_features/v61_features_doc.rst).

- **`encode_jwt` / `decode_jwt` / `ClaimsPolicy`** (`AC_jwt_encode`, `AC_jwt_decode`): the framework had HMAC *file* signing and an ACME-bound RS256 JWS, but nothing to mint/verify a compact bearer JWT. This adds a pure-stdlib HS256/384/512 codec with full claim validation (`exp`/`nbf`/`aud`/`iss`, injectable clock) that drops straight into `http_request`'s bearer auth. Safe by default: rejects `alg:none`, enforces an algorithm allowlist (anti-confusion), and compares signatures with `hmac.compare_digest`. `AC_jwt_decode` returns `{ok, claims}` so flows can branch without raising.

### License Policy Gate

Flag disallowed dependency licenses. Full reference: [`docs/source/Eng/doc/new_features/v60_features_doc.rst`](docs/source/Eng/doc/new_features/v60_features_doc.rst).

- **`evaluate_sbom` / `evaluate_license` / `normalize_spdx` / `license_findings_to_sarif`** (`AC_check_licenses`, `ac_check_licenses`): the SBOM recorded each dependency's license name but never *judged* it. This normalizes license strings to SPDX ids and evaluates them against an allowlist/denylist (with a built-in `DEFAULT_COPYLEFT` set), understanding SPDX expressions (`OR` = choice, `AND` = all), then bridges violations into SARIF (`denied`→error, `unknown`→warning). Pure-stdlib, fully offline — the license-compliance lane beside the OSV vulnerability lane.

### OpenVEX Vulnerability Triage

Suppress the vulns that don't affect you. Full reference: [`docs/source/Eng/doc/new_features/v59_features_doc.rst`](docs/source/Eng/doc/new_features/v59_features_doc.rst).

- **`vex_statement` / `build_vex` / `apply_vex`** (`AC_apply_vex`, `ac_apply_vex`): the OSV scanner surfaces every known CVE forever — there was no way to record "we checked, this one doesn't affect us". This authors [OpenVEX](https://openvex.dev) 0.2.0 statements and applies them to the scanner's findings: `not_affected`/`fixed` **suppress** a finding, `affected`/`under_investigation` **annotate** it. Statements join on the vuln id *or* an alias, optionally product-scoped; `not_affected` requires a justification or impact statement. Pure-stdlib; chains directly after `AC_scan_vulns`.

### Dependency Vulnerability Scanning (OSV)

Match the SBOM against known CVEs. Full reference: [`docs/source/Eng/doc/new_features/v58_features_doc.rst`](docs/source/Eng/doc/new_features/v58_features_doc.rst).

- **`scan_components` / `match_package` / `is_affected` / `findings_to_sarif`** (`AC_scan_vulns`, `ac_scan_vulns`): `build_sbom` only *inventoried* dependencies and `to_sarif` only *exported* findings — nothing ever **produced** a vulnerability finding. This matches the SBOM's `(ecosystem, name, version)` components against an [OSV](https://osv.dev) advisory database (sweeping `introduced`/`fixed`/`last_affected` ranges, PEP-503 name normalization, severity→SARIF level) and bridges results into the existing SARIF exporter for GitHub/Azure DevOps code scanning. The advisory DB is **injected as data** (offline, deterministic); the live `osv.dev` query is an optional `fetcher` seam. Pure-stdlib `re`.

### JSON Schema Validation

Validate nested JSON against a real schema. Full reference: [`docs/source/Eng/doc/new_features/v57_features_doc.rst`](docs/source/Eng/doc/new_features/v57_features_doc.rst).

- **`validate_json` / `is_valid` / `assert_schema`** (`AC_validate_json`, `ac_validate_json`): the framework only *generated* JSON Schema and `data_quality` is a flat per-column checker — neither could validate a nested API request/response body. This adds the consumer: a JSON Schema (Draft 2020-12 subset) validator that reports **every** violation as `{path, keyword, message}` (e.g. `$.age maximum`). Covers `type` (incl. integral-float `integer`), `enum`/`const`, numeric/string bounds, array & object keywords, `allOf`/`anyOf`/`oneOf`/`not`, boolean schemas and local `$ref`. Pure-stdlib `re`; pairs with `json_query` and the `http_request` helper.

## What's new (2026-06-20)

### SARIF 2.1.0 Findings Export

Unify scanner findings for GitHub code scanning. Full reference: [`docs/source/Eng/doc/new_features/v56_features_doc.rst`](docs/source/Eng/doc/new_features/v56_features_doc.rst).

- **`to_sarif` / `write_sarif` / `make_finding` / `from_lint_issues` / `from_audit_findings`** (`AC_export_sarif`, `ac_export_sarif`): the framework's findings producers (action-lint, secrets scan, WCAG audit, guardrail) had no common export. This builds a SARIF 2.1.0 document — with auto rule catalog and stable `partialFingerprints` for cross-run dedupe — that GitHub/Azure DevOps code scanning ingests as line-anchored alerts. Pure-stdlib `json`+`hashlib`; adapters normalize the existing lint/audit shapes.

### Text PII Detection & Redaction

Mask PII in text before it leaks. Full reference: [`docs/source/Eng/doc/new_features/v55_features_doc.rst`](docs/source/Eng/doc/new_features/v55_features_doc.rst).

- **`detect_pii` / `redact_pii_text`** (`AC_detect_pii` / `AC_redact_pii`, `ac_*`): image redaction existed but text (OCR, clipboard, LLM I/O, logs) had no string-level PII handling. This detects emails / phones / SSNs / credit cards / IPv4 / IBANs over plain text and redacts with `label` / `mask` / `partial` / `hash`. Overlapping spans dedupe (a card isn't also a phone); patterns are backtracking-safe. Pure-stdlib `re`+`hashlib`.

### Self-Healing Locator Write-Back

Persist corrected locators so heals aren't forgotten. Full reference: [`docs/source/Eng/doc/new_features/v54_features_doc.rst`](docs/source/Eng/doc/new_features/v54_features_doc.rst).

- **`RepairStore` / `repair_from_heal`** (`AC_repair_record` / `AC_repair_resolved` / `AC_repair_pending` / `AC_repair_approve`, `ac_*`): runtime self-healing previously **threw away** the corrected location, so every run re-healed. This records the corrected locator (coords/VLM description/method) from a heal, **auto-applies** it when `confidence >= auto_threshold` (default 0.9) or queues a reviewable suggestion, and `resolved(key)` returns the learned fix for reuse. Closes the heal→durable-fix loop; pure-stdlib, fully testable.

### DMN-Style Decision Tables

Externalize branching into reviewable rule tables. Full reference: [`docs/source/Eng/doc/new_features/v53_features_doc.rst`](docs/source/Eng/doc/new_features/v53_features_doc.rst).

- **`evaluate_table` / `DecisionTable`** (`AC_decision_table`, `ac_decision_table`): replaces nested `AC_if_var` chains with rows of `conditions -> outputs` and a hit policy (`UNIQUE`/`FIRST`/`PRIORITY`/`COLLECT`). Cell conditions are wildcard / literal / `{op, value}` using the executor's standard comparators (reused, not duplicated). Pure-stdlib, fully testable; the DMN way to keep business rules data-driven.

### Saga / Compensating Rollback

Undo completed steps when a later one fails. Full reference: [`docs/source/Eng/doc/new_features/v52_features_doc.rst`](docs/source/Eng/doc/new_features/v52_features_doc.rst).

- **`Saga` / `run_saga`** (`AC_run_saga`, `ac_run_saga`): records a compensating action per step; on any failure runs the completed steps' compensations in **LIFO** order — the durable-transaction primitive `AC_try` (single-block) couldn't provide. Forward actions/compensations are callables (or JSON action lists), so it's fully unit-tested with no side effects; compensation is best-effort (a failing undo is logged, rollback continues). Returns `{ok, completed, compensated, failed_step, error}`.

### JSONPath Querying

Query API/DB JSON with wildcards, recursion, filters. Full reference: [`docs/source/Eng/doc/new_features/v51_features_doc.rst`](docs/source/Eng/doc/new_features/v51_features_doc.rst).

- **`json_query` / `json_query_one` / `json_extract`** (`AC_json_query` / `AC_json_extract`, `ac_*`): the executor's path walker only split on `.` and indexed — this adds a JSONPath subset (`$`, `.key`, `[n]`/`[-n]`, `*`/`[*]`, `..` recursive descent, `[?(@.k op v)]` filters) over parsed JSON, so array-bearing API/DB responses are easy to extract from. `json_extract` runs a `{key: path}` mapping into a flat dict. Pure-stdlib `re`; the path engine `AC_http_to_var` and DB-row flows were missing.

### Multi-Channel Webhook Notifications

Alert Teams/Discord/Slack/webhook. Full reference: [`docs/source/Eng/doc/new_features/v50_features_doc.rst`](docs/source/Eng/doc/new_features/v50_features_doc.rst).

- **`notify_webhook` / `WebhookChannel`** (`AC_notify_webhook`, `ac_notify_webhook`): `notify` was desktop-toast only and ChatOps shipped Slack only — this sends to **Slack / Discord / Microsoft Teams / raw** webhooks, building the transport-shaped payload (Slack & Teams MessageCard use `text`, Discord uses `content`) and POSTing via the egress-guarded HTTP client. The `poster` transport is injectable (or `set_default_poster`), so sending is unit-tested with no network.

### Outbound CloudEvents Emitter

Emit run/automation events as CloudEvents. Full reference: [`docs/source/Eng/doc/new_features/v49_features_doc.rst`](docs/source/Eng/doc/new_features/v49_features_doc.rst).

- **`to_cloudevent` / `EventEmitter` / `post_cloudevent`** (`AC_emit_event`, `ac_emit_event`): the repo could receive webhooks but not **emit** events — this wraps run-lifecycle/assertion/failure data in a CloudEvents 1.0 (CNCF) envelope and optionally POSTs it over the egress-guarded HTTP client (interop with Knative, Azure Event Grid, iPaaS, generic webhooks). The `sink`/`poster` transport is injectable, so emission is unit-tested with no network.

### Environment-Scoped Typed Asset Store

Per-environment typed config + credential refs. Full reference: [`docs/source/Eng/doc/new_features/v48_features_doc.rst`](docs/source/Eng/doc/new_features/v48_features_doc.rst).

- **`AssetStore` / `active_environment`** (`AC_set_asset` / `AC_get_asset` / `AC_list_assets`, `ac_*`): the orchestrator "Assets/lockers" pillar — centrally-managed config values that differ by environment (dev/staging/prod) and carry a type (`text`/`int`/`bool`/`credential`). `get` coerces to the declared type and falls back to the default env; `credential` assets hold a secret *reference* that `resolve` turns into the real value via an injected resolver (Python-only, so secrets never enter `get`/executor records). Fills the gap the secret vault (secret-only) and config-sync (whole-blob) left.

### Task / Process Mining (Automation-Candidate Discovery)

Discover what to automate from recorded action logs. Full reference: [`docs/source/Eng/doc/new_features/v47_features_doc.rst`](docs/source/Eng/doc/new_features/v47_features_doc.rst).

- **`mine_action_log` / `find_repeated_sequences` / `directly_follows` / `rank_automation_candidates`** (`AC_mine_actions`, `ac_mine_actions`): mines a recorded action log for frequent, repeatable command n-grams, builds a directly-follows graph, and ranks automation candidates by `count × length` — the RPA "task mining" pillar AutoControl recorded data for but never analysed. Pure-stdlib; operates on the existing action-list shape; a candidate that recurs and spans several steps is a strong "extract into a skill" signal.

### Stuck-Loop Guard (Agent Loop Progress Detection)

Catch agents stuck in no-progress loops. Full reference: [`docs/source/Eng/doc/new_features/v46_features_doc.rst`](docs/source/Eng/doc/new_features/v46_features_doc.rst).

- **`LoopGuard` / `digest_result`** (`AC_loop_guard_observe` / `AC_loop_guard_reset`, `ac_*`): the top computer-use failure mode is an agent repeating an action with no effect — and the model can't see its own loop. `LoopGuard` watches the `(tool, args, result)` stream and flags `repeat` (same call N times), `ping_pong` (A-B-A-B), and `no_op` (observation digest unchanged), escalating `ok`→`warn`→`critical` by run length. Complements the step/time budget and offline trajectory eval; pure-stdlib, deterministic.

### Coordinate-Space Mapping (Model Grid ⇄ Physical Pixels)

Translate computer-use model clicks to real pixels. Full reference: [`docs/source/Eng/doc/new_features/v45_features_doc.rst`](docs/source/Eng/doc/new_features/v45_features_doc.rst).

- **`CoordinateSpace` / `xga_space` / `normalized_space` / `downscale_png`** (`AC_to_physical` / `AC_to_model`, `ac_*`): computer-use/VLA models click in a fixed grid (Anthropic downscales to XGA; Gemini returns a 1000×1000 grid), not physical pixels. This maps both ways (round + clamp), `xga_space` aspect-preserves without upscaling, and `downscale_png` resizes a screenshot to the model's input size (Pillow, already core). Pure-arithmetic mapping — unit-tested without a model/GPU.

### Voice-Command Router

Trigger flows hands-free from recognized speech. Full reference: [`docs/source/Eng/doc/new_features/v44_features_doc.rst`](docs/source/Eng/doc/new_features/v44_features_doc.rst).

- **`VoiceRouter`** (`AC_voice_register` / `AC_voice_dispatch` / `AC_voice_list` / `AC_voice_clear`, `ac_*`): map spoken trigger phrases to `AC_*` action lists; feed it recognized text and it runs the closest registered command (phrase matching reuses the fuzzy matcher, so "save the file" fires "save file"). **Speech-to-text is out of scope and injectable** — the router takes text and a `recognizer`/`runner` callable, so routing is fully unit-tested without audio or any speech dependency (a real Vosk/mic recogniser plugs into `listen_once`).

### Locale-Aware Number, Currency & Date Parsing

Parse localized numbers/currency/dates. Full reference: [`docs/source/Eng/doc/new_features/v43_features_doc.rst`](docs/source/Eng/doc/new_features/v43_features_doc.rst).

- **`parse_decimal` / `parse_number` / `format_decimal` / `format_currency` / `format_date`** (`AC_parse_decimal` / `AC_parse_number` / `AC_format_decimal` / `AC_format_currency` / `AC_format_date`, `ac_*`): OCR/UI text like `"1.234,56"` (de_DE) parses correctly to `1234.56` via **Babel**'s CLDR data, and values format back per-locale. `babel` is an optional `[locale]` extra, imported lazily; functional tests run under `importorskip` (wiring/facade always verified).

### Perceptual-Hash Image Dedupe

Collapse near-identical screenshots. Full reference: [`docs/source/Eng/doc/new_features/v42_features_doc.rst`](docs/source/Eng/doc/new_features/v42_features_doc.rst).

- **`average_hash` / `dhash` / `hamming_distance` / `images_similar` / `dedupe_images`** (`AC_image_hash` / `AC_dedupe_images`, `ac_*`): perceptual hashing maps visually similar images to close fingerprints, so near-duplicate frames in a recording or step report cluster by Hamming distance and collapse to one representative. Uses **Pillow** (already core — no extra dep); the dedupe/compare logic is pure Python with an injectable `hasher`, so clustering is unit-tested without any image and the real Pillow path under `importorskip`.

### S3-Compatible Artifact Store

Push run artifacts to object storage. Full reference: [`docs/source/Eng/doc/new_features/v41_features_doc.rst`](docs/source/Eng/doc/new_features/v41_features_doc.rst).

- **`S3ArtifactStore`** (`AC_s3_upload` / `AC_s3_download` / `AC_s3_list` / `AC_s3_delete`, `ac_*`): upload/download/list/delete reports, screenshots, and recordings against any S3-compatible bucket (AWS S3, MinIO, R2). `boto3` is an **optional** `[s3]` extra and the client is **injectable**, so the store's logic — and the executor path — are fully unit-tested with a fake client (no boto3/network); the live AWS path is honestly noted as CI-unverifiable. The whole API is relative to the store `prefix`. A module-level default store backs the commands.

### Fuzzy String Matching & Dedupe

Match noisy OCR/UI text robustly. Full reference: [`docs/source/Eng/doc/new_features/v40_features_doc.rst`](docs/source/Eng/doc/new_features/v40_features_doc.rst).

- **`fuzzy_ratio` / `fuzzy_best_match` / `fuzzy_matches` / `fuzzy_dedupe`** (`AC_fuzzy_ratio` / `AC_fuzzy_best_match` / `AC_fuzzy_dedupe`, `ac_*`): score similarity (0..1), pick the closest candidate from a list, or collapse near-duplicates — so a flow can act on "the button that *looks like* Submit" rather than an exact label. The default backend is stdlib `difflib` (**zero extra deps**); the optional `[fuzzy]` extra adds `rapidfuzz` for speed, with scores normalised either way. `ignore_case` and `score_cutoff` supported.

## What's new (2026-06-19)

### Video Step-Overlay Report

Caption screenshots into a walkthrough video. Full reference: [`docs/source/Eng/doc/new_features/v39_features_doc.rst`](docs/source/Eng/doc/new_features/v39_features_doc.rst).

- **`write_step_video`** (`AC_write_step_video`, `ac_write_step_video`): turns per-step screenshots into a shareable video where each frame is held for a few seconds with its caption and a pass/fail colour banner burned in. The assembly logic (`build_overlay_plan` / `render_overlay_frame`) is separated from OpenCV via injectable `loader`/`drawer`/`writer_factory` hooks — unit-testable with fakes and no `cv2`/`numpy` dependency; the real path lazily imports `cv2` only when those hooks are absent. The visual companion to the HTML/JSON reports.

### Agent Observability (GenAI OpenTelemetry Spans)

OTel GenAI-convention spans for LLM runs. Full reference: [`docs/source/Eng/doc/new_features/v38_features_doc.rst`](docs/source/Eng/doc/new_features/v38_features_doc.rst).

- **`AgentTrace`** (`AC_trace_record` / `AC_trace_summary` / `AC_trace_export` / `AC_trace_reset`, `ac_*`): records spans whose attributes follow the OpenTelemetry **GenAI semantic conventions** (`gen_ai.operation.name`, `gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`/`output_tokens`, `gen_ai.tool.name`) and the `"{operation} {model}"` span name. `to_otel()` drops into an OTLP exporter; `summary()` rolls up token cost and latency; an `operation()` context manager times live blocks and marks errors. Pure-stdlib (no `opentelemetry` dep), injectable clock; pairs with trajectory evaluation (record here, score there).

### Compliance Control Report (SOC2 / ISO 27001)

Map governance evidence to named controls. Full reference: [`docs/source/Eng/doc/new_features/v37_features_doc.rst`](docs/source/Eng/doc/new_features/v37_features_doc.rst).

- **`build_compliance_report`** (`AC_compliance_report`, `ac_compliance_report`): the framework already ships the controls an auditor cares about — egress allowlist, JIT credential leases, maker-checker approval, secrets scanner, audit logging, CycloneDX SBOM. This maps a flat `evidence` mapping to SOC2 (CC6.1/CC6.3/CC6.8/CC7.3/CC8.1) and ISO 27001 (A.5.23/A.8.16/A.8.30) controls, each marked `satisfied`/`gap`/`not_assessed`, and renders JSON or a standalone HTML table. The capstone of the governance set — a reporting aid, not a certification.

### Agent Trajectory Evaluation

Score an agent run against a rubric. Full reference: [`docs/source/Eng/doc/new_features/v36_features_doc.rst`](docs/source/Eng/doc/new_features/v36_features_doc.rst).

- **`evaluate_trajectory`** (`AC_evaluate_trajectory`, `ac_evaluate_trajectory`): scores a recorded trajectory (ordered `{action, args, observation}` steps) against a declarative rubric — `required_actions` (+`ordered`), `forbidden_actions`, `max_steps`, `success_contains`. Returns `{passed, score, steps, checks}` where `score` is the fraction of applicable checks passed and each `check` pinpoints a violated expectation. A deterministic, dependency-free signal for agent regression testing; the rubric is plain data so it lives in JSON action files and travels over MCP.

### Approval Testing (Golden-Master Baselines)

Lock outputs against a human-approved baseline. Full reference: [`docs/source/Eng/doc/new_features/v35_features_doc.rst`](docs/source/Eng/doc/new_features/v35_features_doc.rst).

- **`verify_artifact` / `approve_artifact`** (`AC_verify_artifact` / `AC_approve_artifact` / `AC_pending_artifacts`, `ac_*`): golden-master / snapshot testing for *any* artifact (text, JSON, OCR output, screenshot bytes). `verify_artifact` compares produced content to `<name>.approved.<ext>`; a mismatch or missing baseline writes `<name>.received.<ext>` for review and fails, and `approve_artifact` promotes a reviewed received file to the baseline. Complements pixel diffing with a review-gated baseline you commit alongside the test; names are path-traversal-checked.

### Network Egress Allowlist Guard

Pin which hosts automation may reach. Full reference: [`docs/source/Eng/doc/new_features/v34_features_doc.rst`](docs/source/Eng/doc/new_features/v34_features_doc.rst).

- **`EgressPolicy` / `set_egress_policy`** (`AC_egress_allow` / `AC_egress_check` / `AC_egress_reset`, `ac_*`): an allow list (default-deny) and/or deny list of `fnmatch` host globs (`*.example.com`) consulted by **every** `http_request` (so `AC_http` and all features built on it are covered at once). Blocked hosts raise `EgressBlocked` *before* a socket opens. Starts in allow-all mode — no behavior change until an operator locks egress down. Closes the exfiltration surface for unattended automation.

### Just-In-Time Credential Leases

Zero standing privilege for secrets. Full reference: [`docs/source/Eng/doc/new_features/v33_features_doc.rst`](docs/source/Eng/doc/new_features/v33_features_doc.rst).

- **`CredentialBroker`** (`AC_lease_secret` / `AC_lease_valid` / `AC_revoke_lease` / `AC_lease_active`, `ac_*`): a consumer takes a short-lived *lease* (token bound to a secret name + expiry); the real value is fetched only at `redeem` time, only while valid, through a pluggable resolver (an unlocked `SecretManager`, env, vault). Secret values never enter executor/MCP records — the executor/MCP/Builder surfaces manage the lease lifecycle only; `redeem` is a deliberate Python-API-only escape hatch. Clock and resolver injectable.

### Maker-Checker Approval Gate

Segregation of duties for high-risk steps. Full reference: [`docs/source/Eng/doc/new_features/v32_features_doc.rst`](docs/source/Eng/doc/new_features/v32_features_doc.rst).

- **`ApprovalGate`** (`AC_approval_request` / `AC_approval_approve` / `AC_approval_reject` / `AC_approval_status`, `ac_*`): a *maker* files a high-risk action and gets a token; a *checker* — required to be a **different** principal — approves or rejects it; the action proceeds only once `is_approved` is true. State is an optional shared JSON file so the dispatcher and the human approver can run as separate processes. Pure-stdlib, SOC2-style four-eyes control.

### Plugin SDK

Third-party `AC_*` commands via entry points. Full reference: [`docs/source/Eng/doc/new_features/v31_features_doc.rst`](docs/source/Eng/doc/new_features/v31_features_doc.rst).

- **`discover_plugins` / `load_plugins`** (`AC_list_plugins` / `AC_load_plugins`, `ac_*`): a pip package registers new executor commands declaratively in the `je_auto_control.commands` entry-point group; AutoControl discovers and registers them at runtime (immediately usable from JSON flows, socket server, scheduler, MCP). Broken plugins are skipped; the declarative, namespaced complement to the runtime path loader.

### MCP Structured Output

MCP 2025-06-18 structured tool output. Full reference: [`docs/source/Eng/doc/new_features/v30_features_doc.rst`](docs/source/Eng/doc/new_features/v30_features_doc.rst).

- **`MCPTool(output_schema=...)`** — a tool may declare an `outputSchema`; its dict result is returned as `structuredContent` in the `tools/call` response so clients/LLMs consume a typed, schema-validated object instead of re-parsing text. `to_descriptor()` advertises it in `tools/list`; non-dict results and schema-less tools are unchanged. `ac_validate_rows` is the first built-in to adopt it.

### Tweened Drag

Deterministic eased drags. Full reference: [`docs/source/Eng/doc/new_features/v29_features_doc.rst`](docs/source/Eng/doc/new_features/v29_features_doc.rst).

- **`tween_points` / `tween_drag` / `easing_names`** (`AC_tween_drag`, `ac_tween_drag`): drag from `start` to `end` along an eased curve (linear / ease_in_out_quad / ease_out_cubic / ease_in_cubic) — deterministic, pure-math path, injectable sink for tests; complements the humanized jitter.

### Process-Doc (SOP) Generator

Turn an action list into a step-by-step SOP. Full reference: [`docs/source/Eng/doc/new_features/v28_features_doc.rst`](docs/source/Eng/doc/new_features/v28_features_doc.rst).

- **`generate_sop` / `write_sop`** (`AC_generate_sop`, `ac_generate_sop`): map a recorded/authored action list to numbered, human-readable steps + an HTML document (UiPath Task-Capture deliverable); content HTML-escaped, unknown commands degrade gracefully.

### Heal Analytics & Secret Scan

Two pure-stdlib audit/analysis tools. Full reference: [`docs/source/Eng/doc/new_features/v27_features_doc.rst`](docs/source/Eng/doc/new_features/v27_features_doc.rst).

- **Self-heal analytics** — `analyze_heal_log` / `heal_stats` (`AC_heal_stats`, `ac_heal_stats`): aggregate the self-heal log into heal-rate, strategy mix, fallback-rate, avg latency and the most-brittle locators — catch decaying selectors before they fail.
- **Secret scan** — `scan_secrets(data)` (`AC_scan_secrets`, `ac_scan_secrets`): flag hardcoded secrets in action JSON (by key name, value pattern, or high entropy) that should use `${secrets.*}`; vault refs ignored, previews masked.

### CI Annotations & Clipboard History

Two pure-stdlib utilities. Full reference: [`docs/source/Eng/doc/new_features/v26_features_doc.rst`](docs/source/Eng/doc/new_features/v26_features_doc.rst).

- **CI annotations** — `emit_annotations(results)` (`AC_ci_annotations`, `ac_ci_annotations`): turn result dicts into GitHub Actions workflow commands (`::error file=...,line=...::msg`) so failures show inline in a PR, no reporter action needed.
- **Clipboard history** — `ClipboardHistory` / `default_clipboard_history` (`AC_clip_history_capture`/`list`/`search`/`start`/`stop`, `ac_clip_history_*`): a capped, searchable, newest-first ring buffer of copied text with an optional background poller.

### Resilience Primitives

Reusable retry + circuit-breaker primitives. Full reference: [`docs/source/Eng/doc/new_features/v25_features_doc.rst`](docs/source/Eng/doc/new_features/v25_features_doc.rst).

- **RetryPolicy** — `RetryPolicy(...).run(fn)` / `retry_call(fn)`: retry on configured exceptions with exponential backoff (injectable sleep). (The existing `AC_retry` flow command already retries an action body; this is the reusable callable wrapper.)
- **CircuitBreaker** — `CircuitBreaker` / `CircuitOpenError` (`AC_circuit_call`, `ac_circuit_call`): open after N consecutive failures, short-circuit until a reset timeout, then half-open — stops a retry storm hammering a downed dependency. Injectable clock; `AC_circuit_call` runs an action list through a named breaker.

### Timed Input Macros

Replay input with timing fidelity + a press-hold-release DSL, full stack. Full reference: [`docs/source/Eng/doc/new_features/v24_features_doc.rst`](docs/source/Eng/doc/new_features/v24_features_doc.rst).

- **Timed timeline replay** — `replay_timeline(events, speed=...)` (`AC_replay_timeline`, `ac_replay_timeline`): replay events honoring each `delta_ms` gap, scaled by `speed` and clampable; ops = move/click/scroll/press/release/key.
- **Input-sequence DSL** — `run_sequence(steps)` (`AC_input_sequence`, `ac_input_sequence`): declarative press/hold/release chords + `repeat`/`wait`. Both inject sink+sleep for deterministic tests.

### Semantic Screen State

The semantic companion to the pixel diff, full stack. Full reference: [`docs/source/Eng/doc/new_features/v23_features_doc.rst`](docs/source/Eng/doc/new_features/v23_features_doc.rst).

- **Snapshot & diff** — `snapshot` / `diff_snapshots` / `snapshot_screen` / `screen_changed` (`AC_screen_snapshot` / `AC_screen_diff` / `AC_screen_changed`, `ac_*`): normalize the a11y tree to `{role, name, bbox}` and report what **appeared / vanished / moved** with a human-readable summary — the feedback signal an agent needs to verify a step ("Save dialog appeared").
- **Describe the screen** — `describe_screen` (`AC_describe_screen`, `ac_describe_screen`): a compact "where am I" — role counts + interactive control labels.

### Set-of-Marks Overlay

The standard VLM-grounding format, full stack. Full reference: [`docs/source/Eng/doc/new_features/v22_features_doc.rst`](docs/source/Eng/doc/new_features/v22_features_doc.rst).

- **Number elements** — `mark_elements` / `render_marks` / `resolve_mark` (pure + Pillow): assign `1..N` to interactable elements (with centre/role/text), draw numbered red boxes on a screenshot, and map a chosen number back to its element — so a VLM picks a *number* instead of guessing pixels (directly strengthens the existing VLM locator).
- **Mark-then-click loop** — `mark_screen(render_path=...)` / `mark_click(n)` (`AC_mark_screen` / `AC_mark_click`, `ac_*`): number the live a11y tree (+ optional overlay screenshot), feed marks+image to a model, then click mark `n`.

### Checkpoint & Resume

Durable execution for long flows + a `py.typed` marker, full stack. Full reference: [`docs/source/Eng/doc/new_features/v21_features_doc.rst`](docs/source/Eng/doc/new_features/v21_features_doc.rst).

- **Flow checkpoint & resume** — `run_resumable(actions, run_id=..., store=...)` / `CheckpointStore` (`AC_run_resumable` / `AC_checkpoint_status` / `AC_checkpoint_clear`, `ac_*`): persist step-index + variables after each step; on re-run with the same `run_id`, fast-forward past completed steps and rehydrate variables — a flow that crashes at step 400 resumes at 400, not 0. Pluggable (SQLite default), cleared on completion.
- **`py.typed` marker** — ships the PEP 561 marker so Mypy/Pyright/Pylance honor AutoControl's inline type hints in downstream code (the repo's typed API was previously invisible to type checkers).

### i18n / l10n Testing

Three pure-stdlib internationalization/localization testing helpers that compound, full stack. Full reference: [`docs/source/Eng/doc/new_features/v20_features_doc.rst`](docs/source/Eng/doc/new_features/v20_features_doc.rst).

- **Pseudo-localization** — `pseudo_localize` / `pseudo_localize_catalog` (`AC_pseudo_localize`, `ac_pseudo_localize`): accent + pad UI strings (placeholders preserved, `⟦…⟧` wrapped) to flush out hardcoded text and pre-stress layout before real translation.
- **Text-overflow detection** — `check_overflow(elements)` (`AC_check_overflow`, `ac_check_overflow`): flag text whose estimated width exceeds its widget bounds (the #1 l10n bug), computed from the a11y bounds AutoControl already reads.
- **Catalog completeness** — `check_catalog(base, target)` (`AC_check_catalog`, `ac_check_catalog`): diff a translation catalog for missing / orphaned / empty keys and placeholder mismatches — a CI gate against blank UI.

### Data Quality

Three pure-stdlib data-quality helpers (the gate between `load_rows`/OCR and downstream entry), full stack. Full reference: [`docs/source/Eng/doc/new_features/v19_features_doc.rst`](docs/source/Eng/doc/new_features/v19_features_doc.rst).

- **Row schema validation** — `validate_rows(rows, schema)` (`AC_validate_rows`, `ac_validate_rows`): declarative per-field rules (type/required/regex/min/max/min_len/max_len/allowed/unique); returns `{ok, valid, invalid, errors}` so bad scraped/OCR data is caught before it corrupts an ERP/form.
- **Field extraction** — `extract_fields(text, fields, patterns)` (`AC_extract_fields`, `ac_extract_fields`): named regex presets (email/url/ipv4/phone/date_iso/amount/hashtag) + custom patterns over free text / OCR blobs.
- **Row masking** — `mask_rows(rows, rules)` (`AC_mask_rows`, `ac_mask_rows`): mask columns before export — `redact` / `hash` (SHA-256) / `partial` (keep last 4); complements the screenshot-only redaction.

### SBOM & Suite Sharding

Two pure-stdlib ops tools (security + scale research angles), full stack. Full reference: [`docs/source/Eng/doc/new_features/v18_features_doc.rst`](docs/source/Eng/doc/new_features/v18_features_doc.rst).

- **CycloneDX SBOM** — `build_sbom` / `write_sbom` (`AC_generate_sbom`, `ac_generate_sbom`): emit a CycloneDX 1.6 dependency SBOM (name/version/purl/license) for supply-chain compliance (EU CRA / EO 14028); `root` limits to a package's closure, `extra_components` inventories action files. No third-party dependency.
- **Duration-aware suite sharding** — `shard_flows` / `merge_results` (`AC_shard_suite` / `AC_merge_results`): bin-pack flows into N shards balanced by historical per-flow duration (so the slowest worker, not test count, defines runtime), then merge per-shard reports into one rollup.

### Reactive Observer

A non-blocking screen observer (SikuliX `observe` model), full stack (facade, `AC_*`, MCP, Script Builder). Full reference: [`docs/source/Eng/doc/new_features/v17_features_doc.rst`](docs/source/Eng/doc/new_features/v17_features_doc.rst).

- **`ScreenObserver`** (`AC_observe_add` / `AC_observe_remove` / `AC_observe_list` / `AC_observe_poll` / `AC_observe_start` / `AC_observe_stop`, `ac_observe_*`): register watches that fire on **appear** / **vanish** / **change** of an image/text/pixel and run a callback or action list — react to dialogs/progress/status while the main flow continues.
- **Testable by design** — detection is an injectable `predicate`; transition logic is unit-tested via `poll_once()` with synthetic values. Built-in `image_predicate` / `text_predicate` / `pixel_predicate` wrap the existing locate/OCR/pixel helpers.

### WCAG 2.2 Audit

The accessibility audit gains a WCAG 2.2 / EN 301 549 success-criterion layer, full stack (facade, `AC_*`, MCP, Script Builder). Full reference: [`docs/source/Eng/doc/new_features/v16_features_doc.rst`](docs/source/Eng/doc/new_features/v16_features_doc.rst).

- **WCAG-tagged conformance audit** — `wcag_audit(level="AA")` (`AC_wcag_audit`, `ac_wcag_audit`): tags every defect with its WCAG success-criterion id/level/impact (4.1.2, 1.4.3, 1.4.10) and returns a conformance report with `by_criterion`/`by_impact` counts, filtered to A/AA/AAA — mappable to EN 301 549 for EAA compliance evidence.
- **Target Size (SC 2.5.8)** — `audit_target_size(elements, min_px=24)`: new WCAG 2.2 rule flagging interactive targets smaller than 24×24 px, computed from element bounds; `tag_issue` adds SC tagging to any existing audit issue.

### Memory & Determinism

Two pure-stdlib tools from the agent/QA research round, full stack (facade, `AC_*`, MCP, Script Builder). Full reference: [`docs/source/Eng/doc/new_features/v15_features_doc.rst`](docs/source/Eng/doc/new_features/v15_features_doc.rst).

- **Agent episodic memory** — `AgentMemory` (`AC_memory_remember` / `AC_memory_recall` / `AC_memory_recent` / `AC_memory_forget` / `AC_memory_stats`, `ac_memory_*`): SQLite store of `(goal → trajectory → outcome)` episodes with keyword recall to inject past experience into the planner's context — cross-run learning, no embedding dependency.
- **Deterministic run** — `DeterministicRun` / `seed_everything` (`AC_seed_everything`, `ac_seed_everything`): pin the RNG seed and freeze `time.time` for a `with` block (recording the choices for replay) to kill time/randomness flakiness; `time.monotonic` left intact so timeouts still work.

### Office I/O

Headless read/write for Excel/Word/PowerPoint, full stack (facade, `AC_*`, MCP, Script Builder). Optional extra: `pip install je_auto_control[office]`. Full reference: [`docs/source/Eng/doc/new_features/v14_features_doc.rst`](docs/source/Eng/doc/new_features/v14_features_doc.rst).

- **Excel** — `read_workbook` / `write_workbook` (`AC_read_workbook` / `AC_write_workbook`, `ac_read_workbook` / `ac_write_workbook`): read an `.xlsx` worksheet into row dicts (first row = keys) and write rows back, no GUI.
- **Word** — `read_document` / `write_document` (`AC_read_document` / `AC_write_document`): read/write `.docx` paragraphs.
- **PowerPoint** — `read_presentation` / `write_presentation` (`AC_read_presentation` / `AC_write_presentation`): read per-slide text; write slides as `{title, body:[...]}`.

The backing libraries (`openpyxl`/`python-docx`/`python-pptx`) are optional — each call raises a clear error if missing, and `import je_auto_control` pulls none of them.

### Agent Toolkit

Three pure-stdlib tools for LLM/agent-driven automation, full stack (facade, `AC_*`, MCP, Script Builder). Full reference: [`docs/source/Eng/doc/new_features/v13_features_doc.rst`](docs/source/Eng/doc/new_features/v13_features_doc.rst).

- **Skill / playbook library** — `SkillLibrary` (`AC_skill_save` / `AC_skill_run` / `AC_skill_list` / `AC_skill_remove` / `AC_skill_search`, `ac_skill_*`): store named, reusable action sequences on disk, search them by name/description/tags, and replay across runs — the durable counterpart to in-memory macros.
- **Prompt-injection guardrail** — `assess_text` / `scan_text` / `redact_text` (`AC_guard_text`, `ac_guard_text`): scan untrusted screen/OCR text for injection patterns (instruction-override, system-prompt exfiltration, jailbreak/chat-template markers …) before feeding it to an LLM; returns `{suspicious, score, findings, redacted}`.
- **A2A agent card** — `build_agent_card` / `write_agent_card` (`AC_agent_card`, `ac_agent_card`): publish an A2A agent card so other agents can discover and call AutoControl as a GUI-automation peer.

### Authoring & Debugging

Two pure-stdlib authoring-time tools, full stack (facade, `AC_*`, MCP, Script Builder). Full reference: [`docs/source/Eng/doc/new_features/v12_features_doc.rst`](docs/source/Eng/doc/new_features/v12_features_doc.rst).

- **Element repository** — `ElementRepository` (`AC_element_save` / `AC_element_find` / `AC_element_click` / `AC_element_remove` / `AC_element_list`, `ac_element_*`): save native-UI locators under friendly names (object repository) and reuse them — `repo.click("login.submit")` instead of repeating name/role everywhere; a UI change is fixed in one place.
- **Step debugger / tracer** — `FlowDebugger` (breakpoints, `step`/`continue_`/`run_to_end`, live `variables()`) and `trace_actions` (`AC_debug_trace`, `ac_debug_trace`): step through an action list one command at a time with variables persisting across steps, or get a per-step `{index, command, result}` trace (with `dry_run` to plan without running).

### Test & Tooling Batch

Three pure-stdlib quality-of-life tools, full stack (facade, `AC_*`, MCP, Script Builder). Full reference: [`docs/source/Eng/doc/new_features/v11_features_doc.rst`](docs/source/Eng/doc/new_features/v11_features_doc.rst).

- **Synthetic test data** — `generate_rows(schema, count, seed=...)` / `write_dataset` (`AC_generate_data`, `ac_generate_data`): deterministic fake rows (name/email/phone/int/choice/date…) to drive data-driven runs without real PII; no Faker.
- **MCP registry manifest** — `write_server_manifest("server.json", include_tools=True)` (`AC_mcp_manifest`, `ac_mcp_manifest`): publish a registry-valid `server.json` so MCP agents/IDEs can discover this server.
- **Risk-based test selection** — `rank_flows` / `select_flows` (`AC_rank_tests` / `AC_select_tests`): rank flows by recent failures, flakiness, staleness and never-run from run history; run the riskiest first or only the top-k.

### Transactional Queue

Turn AutoControl from "run a script" into "run a robot." A SQLite-backed work queue implements the production-RPA dispatcher/performer pattern: enqueue items, process one at a time with per-item status, dedup and retry, so a run of thousands is **resumable after a crash** and parallelizable. Pure stdlib, full stack. Full reference: [`docs/source/Eng/doc/new_features/v10_features_doc.rst`](docs/source/Eng/doc/new_features/v10_features_doc.rst).

- **Dispatcher/performer** — `WorkQueue.add()` enqueues (dedupes by reference); `get_next()` atomically claims the oldest item; `complete()` / `fail()` record the outcome. `AC_queue_add` / `AC_queue_next` / `AC_queue_complete` / `AC_queue_fail` / `AC_queue_stats`.
- **Failure semantics** — application errors retry up to `max_retries`; **business** errors (`BusinessError` / `kind="business"`) never retry. `stats()` gives per-status counts for dashboards.

### Unattended Reliability

Three practitioner-pain fixes for unattended / login automation, all headless and full-stack. Full reference: [`docs/source/Eng/doc/new_features/v9_features_doc.rst`](docs/source/Eng/doc/new_features/v9_features_doc.rst).

- **OTP / TOTP for 2FA** — `generate_totp` / `verify_totp` (`AC_otp_to_var`, `ac_generate_otp`): mint the current 6-digit code from a base32 secret to type into a login form (reuses the remote-desktop TOTP engine).
- **Native file dialogs** — `handle_file_dialog` (`AC_handle_file_dialog`): wait for the OS Open/Save/folder dialog, type the path, confirm — in one call, with an injectable driver.
- **Locked-session guard** — `ensure_interactive_session` / `is_session_locked` (`AC_assert_session_active`): fail clearly when the workstation is locked / disconnected instead of emitting phantom clicks.

### Popup Watchdog

The #1 cause of unattended-automation failure is an unexpected dialog the script never coded for (UAC, "session expiring", Windows Update, a modal). The popup watchdog runs a concurrent guard thread that watches for registered patterns and dismisses them independently of the main flow. Surfaced by the practitioner pain-point research as the top unattended failure cause; full stack (facade, `AC_*`, MCP, Script Builder), fully headless. Full reference: [`docs/source/Eng/doc/new_features/v8_features_doc.rst`](docs/source/Eng/doc/new_features/v8_features_doc.rst).

- **Auto-dismiss popups** — `default_popup_watchdog.add_window_rule(title, action="close")` then `.start()` (`AC_watchdog_add` / `AC_watchdog_start` / `AC_watchdog_stop` / `AC_watchdog_list`): closes a matching window or presses a key (`enter`/`esc`) when it appears.
- **Custom rules** — `PopupWatchdog` / `WatchdogRule` pair any detector (image/a11y/text) with a dismisser; a failing rule is logged and skipped, never killing the guard loop.

### Native UI Control

Object-level desktop automation: read and drive native controls through the OS accessibility API (by name / role / app / **AutomationId**) instead of clicking pixels or OCR-ing text — far more reliable for native apps. The accessibility layer previously only listed/found/clicked; it now also acts. Ships through the full stack (facade, `AC_*`, MCP, Script Builder) with a Windows UIAutomation backend; unsupported backends raise a clear error. Full reference: [`docs/source/Eng/doc/new_features/v7_features_doc.rst`](docs/source/Eng/doc/new_features/v7_features_doc.rst).

- **Read / set value** — `control_get_value` / `control_set_value` (`AC_control_get_value` / `AC_control_set_value`): read a textbox/combo value (no OCR) and set it in one call (no per-key typing).
- **Invoke / toggle** — `control_invoke` / `control_toggle` (`AC_control_invoke` / `AC_control_toggle`): press a button or flip a checkbox via its control pattern.
- **Read a table/grid** — `read_control_table` (`AC_read_table`): scrape a grid/list/table control into rows of cell strings — desktop data extraction without OCR.
- Targets a control by `name` / `role` / `app_name` / `automation_id` (the stable Windows identifier), so it survives layout/localization changes.

### Additional updates

Two headless cores that shipped without the rest of their stack are now
first-class. Both gain a facade re-export, an `AC_*` executor command, an
MCP tool, and a Script Builder entry, with headless tests. Full reference:
[`docs/source/Eng/doc/new_features/v6_features_doc.rst`](docs/source/Eng/doc/new_features/v6_features_doc.rst).

- **Visual regression (golden images)** — `take_golden` / `compare_to_golden` (`AC_take_golden` / `AC_assert_visual`): capture a baseline screenshot and fail when the screen drifts beyond a pixel tolerance, with a highlighted diff image and mask regions. `AC_assert_visual` auto-creates the baseline on first run. PIL-only.
- **Finite-state machine** — `run_state_machine` (`AC_run_state_machine`): drive a script as a declarative `{initial, states}` spec whose `on_enter` actions run through the executor and whose transitions fire on `after` / `if_var_eq` / predicate guards, bounded by `max_steps` / `global_timeout_s`.

## What's new (2026-06-18)

Eight headless capabilities that round out scripting, integration, and CI
use: a real command-line interface, recording-to-code generation, and
first-class HTTP / SQL / email / PDF / wait steps. Each ships a headless
Python API, an `AC_*` executor command, an MCP tool, and a visual Script
Builder entry, and is covered by headless tests (network / SMTP / PDF
backends are injected, so nothing touches the outside world). Full
reference page:
[`docs/source/Eng/doc/new_features/v5_features_doc.rst`](docs/source/Eng/doc/new_features/v5_features_doc.rst).

**Command-line interface**
- **`je_auto_control` console script** — run and inspect action files from a shell / CI: `run` (with `--var`, `--dry-run`), `validate` (alias `lint`), `list-commands`, `fmt`, `record`, `codegen`, `version`.

**Code generation**
- **Recording → code** — `generate_code` / `generate_code_file` (`AC_generate_code`, `je_auto_control codegen`) turn a recording or action file into a pytest test, standalone Python, or Robot suite. The default `calls` style emits readable `ac.<fn>(...)` statements, falling back to `ac.execute_action([...])` for flow control.

**Integrations**
- **HTTP / API** — `http_request` (`AC_http_request`): method, headers, JSON or raw body, basic / bearer auth, explicit timeout; non-2xx responses are returned (not raised) so you can assert on status. `AC_http_to_var` now shares the client and can POST bodies.
- **SQL** — `query_sqlite` (`AC_sql_to_var` / `AC_assert_db`): read-only, parameter-bound SQLite queries into a variable, or a scalar assertion (e.g. `SELECT COUNT(*) ... == 0`).
- **Email (SMTP)** — `send_email` (`AC_send_email`): stdlib SMTP with TLS on by default (STARTTLS or implicit SSL over a verified context), attachments, and multiple recipients.
- **PDF** — `extract_pdf_text` / `pdf_metadata` / `assert_pdf_text` (`AC_pdf_to_var` / `AC_assert_pdf_text`): text extraction and content assertions, backed by the optional `pypdf` extra (`pip install je_auto_control[pdf]`).

**Smart waits**
- **Wait for a file** — `wait_until_file` (`AC_wait_for_file`) blocks until a file exists and its size stops growing (a download finished writing).
- **Wait for a TCP port** — `wait_until_port` (`AC_wait_for_port`) blocks until `host:port` accepts connections (pairs with `launch_process`).
- **Wait for a process** — `wait_until_process` (`AC_wait_for_process`) blocks until a process appears or exits — the companion to `launch_process` / `kill_process` (requires psutil).

**Security** — HTTP / SMTP enforce http/https or TLS with verified certificates and explicit timeouts; SQL is read-only and parameter-bound; file paths are resolved before I/O.

## What's new (2026-06-17)

Thirty-plus automation primitives across input realism, vision, flow
control, triggers, window management, and file security — plus recoverable
deletion and an editor undo. Each ships with a headless API, an `AC_*`
executor command, and a visual Script Builder entry; vision and window
features keep their geometry / IO operations injectable so the logic is
fully unit-tested. Full reference page:
[`docs/source/Eng/doc/new_features/v4_features_doc.rst`](docs/source/Eng/doc/new_features/v4_features_doc.rst).

**Human-like input**
- **Human-like mouse motion** — `move_mouse_humanized` walks an eased, bowed cubic-Bezier path with optional overshoot + jitter, deterministic by `seed` (`AC_human_move`).
- **Human-like typing** — `type_text_humanized` types character by character with a jittered per-key delay and optional "thinking" pauses, seedable (`AC_human_type`).

**Vision**
- **VLM natural-language assertion** — `assert_by_description` asks a vision-language model whether the screen matches a description; the `verify()` companion to `locate_by_description` (`AC_assert_vlm`).
- **Scroll-to-find** — `scroll_until_visible` scrolls a direction until a template image or OCR text appears, or the budget runs out (`AC_scroll_to_find`).
- **Region colour stats** — `region_color_stats` reports a region's average + dominant colour and that colour's pixel fraction (`AC_region_color_stats`).
- **QR reading** — `read_qr_codes` decodes QR codes in a screen region via OpenCV's `QRCodeDetector` (no new dependency) (`AC_read_qr`).

**Flow control & variables**
- **Reusable macros** — `AC_define_macro` / `AC_call_macro`: define a named, parameterised action sub-routine once and call it with `${arg}` bindings.
- **In-process parallel** — `AC_parallel` runs branch action lists concurrently, each on an isolated executor so branches never race on shared variables.
- **Performance-budget assertion** — `assert_duration` / `AC_assert_duration` fails a block that takes longer than a millisecond budget.
- **Read into a variable** — `AC_ocr_to_var`, `AC_shell_to_var`, `AC_read_file_to_var`, `AC_http_to_var` (body or dotted JSON path), `AC_now_to_var` (strftime), `AC_random_to_var` (seeded int / float / choice).
- **Transform a variable** — `AC_transform_var`: upper / lower / strip / title / replace / regex-extract / slice, in place or into a new variable.
- **Assert a variable** — `assert_variable` / `AC_assert_var`: eq / ne / lt / gt / contains / regex through the assertion DSL.

**Triggers & smart waits**
- **Composite triggers** — `AllOfTrigger` / `AnyOfTrigger` / `SequenceTrigger` combine any existing trigger by boolean AND / OR / ordered sequence.
- **Cron trigger** — `CronTrigger` fires on a five-field cron expression, composing with the boolean triggers (e.g. "at 09:00 *and* only if the image is on screen").
- **More smart waits** — `wait_until_clipboard_changes` (`AC_wait_clipboard_change`) and `wait_until_window_closed` (`AC_wait_window_closed`).

**Window management**
- **Per-window capture** — `capture_window` screenshots exactly a window's bounds by title (`AC_capture_window`).
- **Layout save / restore** — `save_window_layout` / `restore_window_layout` snapshot every window's position to JSON and move them all back later (`AC_save_window_layout` / `AC_restore_window_layout`).
- **Snap / tile** — `snap_window` moves a window to a screen half, quarter, or maximize (`AC_snap_window`).

**File security & safety**
- **Action-file signing** — `sign_action_file` / `verify_action_file` (HMAC-SHA256 sidecar); `execute_files` can require signatures via `JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS` (`AC_sign_action_file` / `AC_verify_action_file`).
- **Action-file encryption** — `encrypt_action_file` / `decrypt_action_file` (Fernet, AES-128-CBC + HMAC) (`AC_encrypt_action_file` / `AC_decrypt_action_file`).
- **Recoverable deletion** — `move_to_trash` sends a file to the OS recycle bin (Win32 `SHFileOperation` undo flag / macOS Trash / Linux XDG trash, preferring `send2trash`) (`AC_move_to_trash`).

**Reporting & notifications**
- **Screenshot annotation** — `annotate_screenshot` draws labelled boxes / translucent highlights / arrows / text onto a capture (`AC_annotate_screenshot`).
- **Desktop notifications** — `notify` shows a cross-platform toast (notify-send / osascript / PowerShell), injection-safe (`AC_notify`).

**GUI**
- **Recording Editor undo** — every edit is snapshotted; **Ctrl+Z** (and an Undo button) restore the prior state.
- **Triggers tab** — "Combine selected" wraps chosen triggers into a composite; new **Cron** trigger type.
- **Assertions tab** — new **VLM** ("screen matches description") assertion kind.
- Every new `AC_*` command appears in the visual **Script Builder**.

**Fixes** — repaired the USB-passthrough approval-prompt crash on PySide6 6.11.1 (`Q_ARG(object)` → a Qt signal), eight stale / broken GUI + USB tests, two lost exception chains, and brought thirteen functions back under the cyclomatic-complexity gate.

## What's new (2026-06)

Nine additions that turn the automation primitives into a full **QA / test
framework**: assert screen state, drive scripts from data, detect and
quarantine flaky tests, run a scored suite, emit CI-native reports, audit
accessibility / i18n, fan a script across a device matrix, and assert on
audio / video. Each ships with a headless API, an `AC_*` executor command,
an `ac_*` MCP tool, and a Qt GUI tab. Full reference page:
[`docs/source/Eng/doc/new_features/v3_features_doc.rst`](docs/source/Eng/doc/new_features/v3_features_doc.rst).

**Assertions**
- **Assertion DSL** — verify screen state instead of only driving it: `assert_text` (OCR, `regex` + `present=False` for absence), `assert_image`, `assert_pixel`, `assert_window`, `assert_clipboard` (`equals` / `contains` / `regex`, `present=False` to confirm a secret was cleared), `assert_process` (a named process is / isn't running, via psutil). Returns an `AssertionResult`; raises `AutoControlAssertionException` on mismatch with optional failure screenshot (`AC_assert_text / _image / _pixel / _window / _clipboard / _process`).
- **Off-screen assertions** — `assert_file` (existence / substring / SHA-256 / minimum size — verify a download or export) and `assert_http` (an http/https endpoint returns a status + optional body text, always with an explicit timeout). Both extend the DSL beyond the screen and plug into the combinators below (`AC_assert_file / AC_assert_http`).
- **Assertion combinators** — `assert_all([...specs])` runs a batch as *soft assertions* (every spec is checked, all failures collected before raising) and returns a `GroupAssertionResult`; `assert_any([...specs])` is the OR-complement (passes when at least one spec passes, short-circuiting — e.g. *either* a success dialog *or* a redirect confirms a login); `assert_eventually(spec, timeout, interval)` retries one declarative assertion spec until it passes or times out (e.g. poll a health endpoint until it returns 200, or wait for a download file to appear). Both are spec-driven (`{"kind": "text", "text": "Saved"}`, `{"kind": "http", "url": "..."}`) so they work identically from Python, JSON, and MCP across every assertion kind — text/image/pixel/window/clipboard/process/file/http (`AC_assert_all / AC_assert_eventually`).
- **Media assertions** — `assert_audio_activity` (record + RMS threshold for sound vs silence) and `assert_video_changes` (mean frame-to-frame diff over a segment for motion vs static); pure numeric cores, lazy `sounddevice` / OpenCV (`AC_assert_audio / AC_assert_video_changes`).

**Data-driven execution**
- **Data sources** — `load_rows` connectors for CSV / JSON / SQLite / Excel / inline; the `AC_for_each_row` block command runs a body once per row with `${row.column}` access. SQLite is single read-only `SELECT`/`WITH` only; paths are `realpath`-validated. `${var}` interpolation now resolves dotted dict-key / list-index paths while preserving types (`AC_load_data`).

**Flaky detection & quarantine**
- **Flaky report** — score intermittent failures from run history by pass↔fail flip rate, grouped by script / source (`AC_flaky_report`).
- **Quarantine** — a persistent (mode 0600) skip-list the suite runner honours; `auto_quarantine_from_flakiness` auto-populates it above a flip-rate threshold (`AC_quarantine_add / _remove / _list / _clear / _auto`).

**Suite runner + CI reports**
- **QA suite orchestration** — `run_suite` turns action lists into scored cases with setup / teardown, tags, and data-driven expansion; assertion failures → failed, other exceptions → error, quarantined → skipped (`AC_run_suite`).
- **JUnit / Allure reports** — `write_junit_xml` + `write_allure_results` (or `junit_path` / `allure_dir` on `AC_run_suite`) emit reports Jenkins / GitHub Actions / GitLab CI / Allure parse natively.

**Audit, matrix, media**
- **Accessibility / i18n audit** — reuse the a11y tree + OCR to find missing accessible names, WCAG contrast-ratio failures, and ellipsis-truncated strings (`AC_audit_accessibility / AC_audit_contrast`).
- **Mobile device matrix** — fan one action list across many Android / iOS devices in parallel, each on an isolated executor, targeting the current device via `${device.*}`; per-device pass/fail, failures isolated (`AC_run_device_matrix`).

## What's new (2026-05)

Twenty-seven additions covering smarter locators, deeper IDE / ops
tooling, four new platforms (Wayland, Wayland-libei, Android
widget-tree, iOS), screenshot PII redaction, and a generic
plan-execute-verify agent loop. Each ships with a headless API, an
`AC_*` executor command, an `ac_*` MCP tool, and (where it makes
sense) a Qt GUI tab. Full reference page:
[`docs/source/Eng/doc/new_features/v2_features_doc.rst`](docs/source/Eng/doc/new_features/v2_features_doc.rst).

**Locator + selector intelligence**
- **Self-healing locator** — `image_template → VLM` fallback with a JSON-lines audit log (`AC_self_heal_locate / _click`).
- **Anchor-based locator** — find element B by spatial relation (`above`, `below`, `left_of`, `right_of`, `near`) to anchor A; anchor and target can use different backends (image / OCR / VLM / a11y).
- **OCR with structured output** — cluster raw OCR matches into rows, tables, and `label:value` form fields (`AC_ocr_read_structure`).
- **Smart waits** — `wait_until_screen_stable`, `wait_until_pixel_changes`, `wait_until_region_idle`: frame-diff replacements for `time.sleep`.
- **A/B locator framework** — race N strategies for the same target; recommend the historically best one from a persisted ledger.

**Operations + observability**
- **LLM cost telemetry** — per-call token + USD log with day / model / provider rollup (`record_llm_call`, `summarise_llm_costs`).
- **Trace replay UI** — scrubbable timeline over the existing time-travel recordings with per-step action list.
- **Failure → ticket automation** — fan a failure report out to Jira / Linear / GitHub Issues when a scheduled / triggered / REST run fails.
- **Container CI templates** — GitHub Actions + GitLab CI workflows that build the image, run the headless pytest suite under Xvfb, and smoke-test the REST entrypoint; XFCE+x11vnc Dockerfile variant for flows that need a real WM.
- **Cross-host DAG orchestrator** — parallel execution with skip-on-failure cascade across local + admin-console-registered hosts (`run_dag`, `AC_run_dag`).
- **Multi-viewer presence** — roster + controller/observer roles for the remote desktop, with a thread-safe Python `PresenceRegistry` independent of aiortc.

**Agent + integrations**
- **Computer-use high-level API** — `run_computer_use(goal, ...)` wraps `ComputerUseAgentBackend` + `AgentLoop`; auto-detects display size; bounded by `max_steps` / `wall_seconds`.
- **Generic agent loop JSON + MCP** — `AC_run_agent` / `ac_run_agent` expose the closed-loop `AgentLoop` (plan → act → verify → retry) with pluggable Anthropic / OpenAI backends; the Anthropic-only Computer-Use raw path remains via `AC_computer_use`.
- **WebRunner convenience commands** — `web_open` / `web_quit` / `web_screenshot` / `web_current_url` on top of the existing `je_web_runner` bridge; same surface exposed as `AC_web_*` and `ac_web_*`.
- **Chat-ops bot** — transport-agnostic `CommandRouter` + polling Slack adapter. Built-in commands: `/help`, `/scripts`, `/run`, `/screenshot`, `/status`. RBAC via `required_role`.

**Privacy + safety**
- **Screenshot PII redaction** — `RedactionEngine` with built-in detectors for email / credit card / SSN / phone (regex against caller-supplied OCR tokens) plus accessibility-tree secure-text-field detection. Forced regions for sticky overlays. Env-var-driven default policy `JE_AUTOCONTROL_REDACTION=off|moderate|strict`. Wired through `AC_redact_screenshot` + `ac_redact_screenshot`.

**Platform coverage**
- **Wayland CLI backend** — `wtype` / `ydotool` / `grim` with `XDG_SESSION_TYPE` auto-detect and X11 (XWayland) fallback; override via `JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11|wayland|auto`.
- **Wayland libei native** — ctypes binding to `libei.so.*` for microsecond-latency input; opt-in via `JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=libei|cli|auto`. Defaults to libei when loadable.
- **macOS Accessibility deep-dive** — recursive `dump_accessibility_tree()` plus a polling `AccessibilityRecorder` for focus / bounds events.
- **Android — adb shell primitives** — `AC_android_tap/swipe/key/text/screenshot` route through `adb` for any phone over USB / Wi-Fi adb. No daemon required.
- **Android — uiautomator2 widget tree** — `AC_android_find_element/click_element/dump_hierarchy` add selector-based widget lookup (`text` / `resource_id` / `description` / `class_name`) and live XML hierarchy dump on top of the adb path.
- **iOS — XCUITest via WebDriverAgent** — new `je_auto_control.ios.*` namespace: `tap`, `swipe`, `long_press`, `type_text`, `press_key`, `screenshot`, `screen_size`, `find_element` / `click_element` (XCUITest selectors: `name`, `class_name`, `predicate`), `dump_source`. Seven new `AC_ios_*` executor commands and matching `ac_ios_*` MCP tools. `facebook-wda` is an optional pip dep; loads lazily so non-Mac hosts still import the package.

**Developer experience**
- **autocontrol-lsp completion** — the language server now tracks `didOpen` / `didChange` / `didClose`, publishes diagnostics for invalid JSON and unknown `AC_*` commands, and provides signature help generated from the live executor table.
- **`.pyi` stub generator** — `python -m je_auto_control.utils.stubs.generator je_auto_control/actions.pyi` emits an IDE-facing stub so every `AC_*` command autocompletes with parameter hints.
- **VS Code extension** — bundled extension now ships `AutoControl: Run / Screenshot / Preview` commands that hit the local REST API.
- **Browser extension recorder** — Manifest V3 extension under `browser-extension/`: capture clicks, typing, navigation, form submissions in a tab and export them as `AC_web_*` / `WR_*` JSON.
- **pytest plugin + Gherkin BDD** — `pytest11` entry point auto-loads; `@pytest.mark.autocontrol` arms screenshot-on-failure; `bdd_steps.register_pytest_bdd_steps(pytest_bdd)` wires `Given/When/Then` onto every `AC_*` verb.
- **Visual flow editor** — node-based view that round-trips to the same JSON action format the list-based Script Builder uses.

---
