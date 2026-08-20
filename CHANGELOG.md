# Changelog

This file records user-visible compatibility changes. Detailed development
notes remain in `WHATS_NEW.md`.

The format follows Keep a Changelog. Until 1.0, breaking changes are permitted
only when documented here with a migration path.

## Unreleased

### Added

- **The macOS recorder works.** `record()`, `stop_record()`,
  `stop_record_timeline()`, the `AC_record*` commands, the `ac_record_*` MCP
  tools and `je_auto_control record` all run on macOS now; they used to refuse
  outright with "Cannot use recorder on macOS". Capture goes through a
  listen-only Quartz `CGEventTap` on its own thread
  (`je_auto_control.osx.listener.osx_listener.OSXInputTap`), so it records
  presses, releases, the wheel and per-event timing, exactly as the Windows
  hook does. Requires Accessibility permission; without it the tap raises
  `AutoControlRecordException` naming the permission — where the facade's
  `record()` logs it, as it does every other backend's start failure — rather
  than starting a session that silently records nothing.
- `je_auto_control.utils.input_macro.recorder_base` — the platform-neutral
  half of recording: `timeline()`, `legacy_action_queue()` and the
  `InputRecorder` base the Windows and macOS recorders now share.
  `timeline` keeps working when imported from
  `je_auto_control.windows.record.win32_input_hook`, where it used to live.
- Cross-platform window management. The 23 `AC_*` window commands and their
  MCP tools now work on macOS and Linux/X11 as well as Windows, through a
  backend seam (`je_auto_control.wrapper.window_backends`). Wayland remains
  unsupported: the protocol does not let a client enumerate or move another
  application's windows.
- Linux accessibility backend over AT-SPI2
  (`je_auto_control.utils.accessibility.backends.linux_backend`), with no new
  dependency. Serves both X11 and Wayland sessions.
- `je_auto_control.utils.platform_id` — one place that classifies the
  operating system family, and the BSDs are now one of them. FreeBSD, OpenBSD,
  NetBSD and DragonFly route to the X11 backend instead of raising "unknown
  operating system".
- `AutoControlUnsupportedOperationException`, raised when a platform backend
  cannot perform an operation. It subclasses both `AutoControlException` and
  `NotImplementedError`, so existing `except NotImplementedError` handlers are
  unaffected while the executor's containment boundaries now catch it.
- `je_auto_control.utils.dbus_client` — the D-Bus client, moved out of
  `linux_wayland/` so `utils/` can use it. The old path re-exports it.

- Stable, headless `je_auto_control.api` façade.
- Portable `autocontrol.failure-bundle/v1` diagnostic archives and CLI command.
- Public API lifecycle, capability matrix, security policy, coverage and type
  checking configuration.
- Unicode text entry by key injection: `type_unicode_keys`, `type_unicode_text`,
  `plan_unicode_keys`, `unicode_keys_supported` (commands
  `AC_type_unicode_keys` / `AC_type_unicode_text`, MCP tools
  `ac_type_unicode_keys` / `ac_type_unicode_text`), on Windows backend
  primitives `press_unicode` / `release_unicode` / `type_unicode_unit`.
- Cross-word OCR matching helpers `find_spans` / `group_lines`.
- `monitor_layout.grab_logical` / `logical_virtual_rect` / `logical_scale` /
  `needs_rescale` — screen capture in the coordinate space the mouse uses.
- `find_image` / `find_image_multi` accept `all_screens` and `screen_region`.
- `AutoControlFlatTemplateException` (a subclass of `AutoControlScreenException`)
  for a template with too little variation to locate.
- Accessibility search scoping and matching: `window_title` on
  `list_accessibility_elements` / `find_accessibility_element` /
  `click_accessibility_element` / `control_get_state`, a `contains` substring
  mode with exact-name ranking, `find_accessibility_elements`,
  `accessibility_status`, `control_get_state`, and `rank_by_name` (commands
  `AC_a11y_find_all` / `AC_control_get_state`, MCP `ac_a11y_find_all` /
  `ac_control_get_state`). The accessibility GUI tab gains a window filter.
- `AccessibilityElement.enabled`.
- `stop_record_timeline` (`AC_stop_record_timeline`,
  `ac_record_stop_timeline`): the recording as press *and* release, wheel
  movement and `delta_ms`, ready for `replay_timeline`.
- `utils/input_reach`: `input_desktop_available`, `input_reaches_system`
  (`AC_input_reachable`, `ac_input_reachable`) — whether input this process
  sends can actually arrive. The second probe presses F13 to find out.
- `utils/keyboard_layout`: `char_table`, `layout_char_table`, `vk_to_char`,
  `foreground_keyboard_layout` — which character each key produces on the
  active layout, with a US fallback.
- Window management gains the primitives it was missing:
  `minimize_window_by_title`, `foreground_window`, `window_rect` and
  `move_window_by_title` (`AC_minimize_window`, `AC_foreground_window`,
  `AC_window_rect`, `AC_move_window`; `ac_minimize_window`,
  `ac_foreground_window`, `ac_window_rect`). `list_windows` takes
  `titled_only`, and `move_window_by_title` keeps the window's current size
  when width/height are omitted.
- Window ownership: `foreground_window_process_id` and `window_process_id`
  (`AC_foreground_window_pid`, `AC_window_pid`; `ac_foreground_window_pid`,
  `ac_window_pid`; two Script Builder specs), on the Windows backend
  `get_window_process_id`. A title is whatever the application decides to
  display, so it cannot answer "which program is the user actually in front
  of" — the process id can. Unavailable reads as `None` (`{"pid": 0}` on the
  JSON surfaces) rather than a bare `0`, which a caller could otherwise match
  against a process list and hit the System Idle Process.
- Windows by owning process: `windows_for_process_id` and
  `minimize_windows_for_process` (`AC_windows_for_pid`,
  `AC_minimize_windows_for_pid`; `ac_windows_for_pid`,
  `ac_minimize_windows_for_pid`; two Script Builder specs). A multi-process
  application cannot be addressed by title — its windows are named after
  whatever they display and several of its processes have no window at all —
  so ownership is the stable key.
- Input posted to a window without focusing it: `post_key_to_window` and
  `post_click_to_window` (`AC_post_key_to_window`, `AC_post_click_to_window`;
  `ac_post_key_to_window`, `ac_post_click_to_window`; two Script Builder specs),
  on the Windows backend `get_focused_control`, `deepest_child_at`, `post_key`
  and `post_click`. They resolve the window by title *substring* like every
  other function here, and post to the control that actually has keyboard
  focus — or, for a click, to the deepest child under the point, in that
  child's client coordinates. Posting to the top-level frame (what the older
  `send_key_event_to_window` does) types nothing in any application with child
  controls: measured on Character Map, the frame swallowed the key while the
  focused edit accepted it. Both return whether the messages were queued, and
  posting remains best effort — applications reading raw input or checking the
  foreground ignore posted messages.
- `utils/url_canon` reaches its delivery surfaces: `canonicalize_url`,
  `normalize_url`, `urls_equal`, `build_query` and `parse_query` are exported
  from the facade, with `AC_canonicalize_url` / `AC_normalize_url` /
  `AC_urls_equal`, the matching `ac_*` MCP tools, and three Script Builder
  specs. The module and its tests already existed; only the wiring is new.
- `JE_AUTOCONTROL_WAYLAND_POINTER_ACCEL` — how an operator declares what the
  library cannot read back. `flat` says pointer acceleration is off for the
  ydotoold device, so an absolute move through the ydotool fallback is exact
  and needs no warning; `strict` refuses that move instead of letting a click
  land somewhere else; unset (or any unrecognised value, which says so and
  falls back) keeps the existing warn-once-and-move behaviour. The libei path
  is absolute at the protocol level and is not affected either way.

### Removed

- `je_auto_control.linux_wayland._detect.WAYLAND_GDBUS` is gone, along with the
  `gdbus` probe it named: the desktop-portal capture tier no longer shells out
  to any binary. `_detect` is a private module and nothing else referenced the
  constant.
- **Breaking — `je_auto_control.windows.listener` is gone**, with its
  `Win32KeyboardListener` and `Win32MouseListener` classes. Recording moved to
  `windows/record/win32_input_hook.py`, after which nothing in the package or
  the test suite referenced them.
- **Breaking — `je_auto_control.utils.clipboard.clipboard_image` is gone.** Its
  two functions were duplicates of the ones in
  `je_auto_control.utils.clipboard.clipboard`, under identical names but with a
  different `set_clipboard_image` signature, so importing the wrong module
  failed at runtime and only for one of the two argument types. Import from
  `je_auto_control.utils.clipboard` (or the top-level facade) instead; the
  surviving function accepts both PNG bytes and a file path.

### Changed

- The default run-history database is created when it is first written to,
  not while `je_auto_control` is being imported. `HistoryStore` opens its
  connection (and makes its parent directory) on first use, so merely
  importing the package no longer creates
  `~/.je_auto_control/run_history.sqlite`. Every method behaves as before;
  a store that was never used and then closed simply never touched the
  disk.

- **The sign of `scroll_value` picks the scroll direction on every platform.**
  Windows and macOS have always read it that way; X11 and Wayland took the
  direction from `scroll_direction` alone and used `abs(scroll_value)`, so
  `mouse_scroll(-3)` — code written and tested against the Windows convention —
  scrolled *down* three notches on Linux instead of up, with no exception and
  no warning. `scroll_direction` now names the direction a **positive** count
  takes, and a negative count reverses it, on all four backends.

  *Migration.* Code that passed a negative `scroll_value` to Linux or Wayland
  and relied on the magnitude alone now scrolls the opposite way. Take
  `abs()` at the call site to keep the old behaviour:
  `mouse_scroll(abs(value), scroll_direction="scroll_down")`. Code that passed
  a positive count is unaffected, as is every Windows and macOS caller.
- **`import je_auto_control` no longer imports OpenCV, NumPy, Pillow,
  `je_open_cv` or `cryptography`.** They are imported by the functions that use
  them. The facade pulled all five in at module scope, so a platform without
  wheels for them — a FreeBSD desktop, for one — could not use the input
  automation half of the package at all, though it needs none of them. Nothing
  moves in the public API and the packages remain hard dependencies; what
  changes is *when* a missing one is reported, which is now at the first image
  or encryption call rather than at import. `test_facade_import_is_light.py`
  keeps it that way.
- **`macos_record_error_message` now names a permission, not a platform.** It
  read "Cannot use recorder on macOS", which described a limitation that no
  longer exists; it now names the Accessibility grant that recording actually
  needs, and is raised from the event tap rather than from the wrapper.
- **The `xdg-desktop-portal` capture tier no longer needs `gdbus` installed.**
  It speaks D-Bus directly, so `linux_wayland.portal.is_available()` now
  reports whether a session bus address is set rather than whether the `gdbus`
  binary is on `PATH`. This widens where the last-resort tier runs; the install
  hint in the "no capture tool found" error and the `screen_capture`
  diagnostics check were reworded to match.
- **`LibeiBackend.scroll()` sends whole wheel clicks, not raw detent counts.**
  libei measures discrete scroll in 120ths of a click, so the previous call
  asked for 1/120th of the scroll requested and libei logged it as a client
  bug. Measured against a real EIS server (`docker/eis_verify.py`).
- **Wayland `mouse.scroll()` goes through libei where libei is up, instead of
  always shelling out to ydotool.** Motion, buttons and keys already did;
  scroll was held back because its sign was a guess. The two paths count
  wheel detents in opposite directions — this repository's
  `wayland_scroll_direction_*` constants are in the kernel's `REL_WHEEL`
  frame, which is what ydotool writes (positive is up), and libei is in the
  `wl_pointer` frame (positive is down) — so the vertical axis is negated on
  the way to libei and the horizontal one is not. No API change: scrolling on
  a libei host no longer needs ydotool or a uinput daemon at all.
- **A libei emission that a live backend refuses now falls back to the CLI,
  as `libei`'s own docstring already claimed it did.** Only the *connection*
  degraded; a compositor that paused a device, or a session that ended
  between two calls, raised out of `set_position` / `press_key` / `hotkey`
  instead of reaching ydotool. A chord refused part-way releases the keys it
  already pressed before handing over, so no modifier is left held.
- **`LibeiUnavailable` derives from `AutoControlException`** (as well as
  `RuntimeError`, which existing probes catch). It was a bare `RuntimeError`,
  so it escaped every `except AutoControlException` containment boundary —
  the executor, the poll loops, the request handlers and the GUI slots.
- **A libei session that completed its handshake is released instead of
  abandoned.** `ei_unref` segfaults on libei 1.3.901 only for a context whose
  backend opened and whose handshake never progressed; with an EIS peer to
  test against, the live case is measurably safe. Teardown no longer leaks a
  context and a file descriptor per process.

- **`POST /execute` and `POST /execute_file` answer `400`, not `500`, for a
  command name the executor does not know.** Both used to funnel every
  executor failure into `500 {"error": "execute_action failed"}`, so a client
  could not tell a typo in its own request from a broken server. Every name in
  the list — nested flow-control bodies included — is now checked before
  anything runs; an unrecognised one comes back as
  `400 {"error": ..., "unknown_commands": [...]}` naming all of them, and
  nothing was executed. `/execute_file` answers the same way for a path that
  is unreadable or holds something that is not an action list. A client that
  keyed off `500` to detect a bad request must key off `400` instead.
- **Windows clipboard calls wait out a clipboard another process is holding
  open** instead of failing immediately. Only one process may have it open at
  a time, so `RuntimeError: OpenClipboard failed` used to escape whenever
  anything else was mid-copy — roughly one call in a thousand on a live
  desktop. `win32_clipboard_api.open_clipboard()` is the one place that opens
  it now, retrying for about 200 ms; the failure is still raised after that.
  Callers that relied on an immediate failure will see a call take up to
  200 ms longer in the contended case.

- **`send_key_event_to_window` / `send_mouse_event_to_window` now actually
  reach the target.** They posted to the top-level frame, but keyboard messages
  go to the control that *has focus* and a click belongs to the child under the
  point in that child's client coordinates — so for any window with child
  controls they did nothing at all while still reporting success. They delegate
  to `post_key_to_window` / `post_click_to_window`. Two visible consequences:
  the key sender now matches the window title as a *substring* (it required an
  exact title before, via `FindWindowW`), and the mouse sender accepts a title
  string as well as the hwnd it always took.
- `save_window_layout` now snapshots only titled windows (its documented
  behaviour). Untitled entries could never be restored — `restore_window_layout`
  addresses a window by title and skips blank ones — so they only inflated the
  saved count, by roughly half on a real desktop.
- `set_clipboard_image` accepts PNG bytes **or** a path to any Pillow-readable
  image, and `get_clipboard_image` / `set_clipboard_image` are now exported
  from `je_auto_control.utils.clipboard` and the top-level facade, with
  `AC_clipboard_get_image` / `AC_clipboard_set_image` commands. They were
  previously reachable only through MCP and the GUI, not `execute_action`.
- **Breaking — `close_window_by_title` / `AC_close_window` / `ac_close_window`
  now actually close the window** (they post `WM_CLOSE`). They previously
  *minimised* it: the Win32 call underneath is named `CloseWindow` but
  minimises, and the wrapper inherited both the call and the wrong promise, so
  every caller asking to close a window silently got a minimise instead. The
  old behaviour is available unchanged as `minimize_window_by_title` /
  `AC_minimize_window` / `ac_minimize_window`.
- `focus_window` restores a window that is minimised before bringing it to the
  front — focusing a minimised window used to do nothing visible. A maximised
  window is left maximised (`SW_RESTORE` would have un-maximised it).
- `show_window_by_title` no longer calls `SetForegroundWindow` after `SW_HIDE`;
  hiding a window and then pulling it forward are contradictory.
- Releases are prepared from version tags and use PyPI Trusted Publishing.
- The USB/IP server binds `127.0.0.1` by default (least-privilege). Exporting
  the attached device to the LAN now requires an explicit `host="0.0.0.0"`.
- `write` no longer raises on a character missing from the virtual-key table
  where the backend can inject Unicode; it types that character instead.
- `find_text_matches` returns runs of consecutive word boxes, so a target split
  across boxes now matches. Results are merged boxes covering the whole run
  (union rectangle, minimum confidence) rather than one box per word.
- `find_image` / `find_image_multi` search every monitor by default and return
  virtual-desktop coordinates, which are negative when a monitor sits left of or
  above the primary. Pass `all_screens=False` for the previous primary-only
  behaviour.
- `match_template` / `match_template_all` capture every monitor and return
  screen coordinates. A hit found inside a `region` previously came back in
  region-local coordinates; it is now offset by the region's origin. Matches
  against a caller-supplied `haystack` are unchanged (image-local).
- `match_template` / `match_template_all` refuse an almost-single-colour
  template instead of returning an arbitrary position.
- `element_matches` accepts a friendly role name (`"button"`) as well as the
  raw `"ControlType_50000"` the Windows backend reports.
- `AccessibilityBackend.list_elements` takes `window_title`; in-tree backends
  accept it, and the facade only forwards it when set, so an out-of-tree
  backend keeps working until someone asks for scoping.
- `AccessibilityElement.to_dict()` gains an `enabled` key.
- The Windows recorder captures through one low-level hook
  (`Win32InputHook`) instead of the two listeners. `record` / `stop_record`
  keep their behaviour and return shape.
- An unscoped `list_accessibility_elements` walks one top-level window at a
  time in z-order, node by node, and stops at `max_results`, instead of one
  uninterruptible `FindAll` over the whole desktop. Results are therefore
  ordered front-most window first, and a small `max_results` no longer
  reaches windows further back.
- The UIAutomation object is created from `CUIAutomation8` as
  `IUIAutomation2` with a bounded `ConnectionTimeout` where available, so an
  application that never answers UIA can no longer stall a search for a
  minute. Falls back to `CUIAutomation` / `IUIAutomation` otherwise.
- `find_accessibility_elements` / `AC_a11y_find_all` / `ac_a11y_find_all`:
  `max_results` now caps the matches returned (default 50) and the new
  `scan_limit` caps how many elements are examined (default 1500). Callers
  that passed `max_results` expecting a scan bound should pass `scan_limit`.

### Deprecated

- `send_key_event_to_window` and `send_mouse_event_to_window` — use
  `post_key_to_window` / `post_click_to_window`. Both now emit a
  `DeprecationWarning` and delegate to the working implementation; see Changed
  for the behaviour that changes.

- New integrations should avoid the eager, historical top-level import surface
  and import stable entry points from `je_auto_control.api`.

### Fixed

- **A rejected config bundle aborted the rest of the script.** Five
  framework errors still inherited `Exception` directly —
  `ConfigBundleError`, the USB passthrough `ProtocolError`,
  `SessionError` and `UsbClientError`, and the work queue's
  `BusinessError` — and the containment boundaries all catch the
  `AutoControlException` family, so none of them caught these. A
  malformed bundle passed to `AC_config_import` therefore raised straight
  past the executor's per-action boundary and killed every remaining
  action, even under `raise_on_error=False`; `AC_usb_remote_devices` and
  `AC_usb_remote_open` had the same path through `UsbClientError`. All
  five derive from `AutoControlException` now, so they are recorded as a
  failed action like every other framework error. `LoopBreak`,
  `LoopContinue` and the MCP dispatcher's private error carrier stay
  outside the family deliberately — they are control flow, not failure.
- **`import je_auto_control` needed a Python built with `sqlite3`, and
  FreeBSD's is not.** `sqlite3` is in the standard library but not in every
  build of it: CPython links it against a system library, and FreeBSD ships
  the result as the separate `databases/py-sqlite3` package. Ten subsystems
  imported it at module scope — run history, checkpoints, the work queue,
  agent memory, the remote-desktop audit log, SQL data sources, and the
  error tuples in the REST, chat-ops and MCP containment boundaries — and
  all ten are reachable from the facade, so the whole package failed to
  import on a stock FreeBSD, mouse and keyboard included. They go through
  `je_auto_control.utils.sqlite_support` now, which fails at the first call
  that opens a database rather than at import, and raises
  `AutoControlUnsupportedOperationException` — the type the GUI tabs, the
  REST handler and the executor already report as "not available here" —
  instead of an `ImportError` none of them catch. `run_diagnostics()` lists
  `sqlite3` among the optional dependencies, so the gap is visible without
  reading a traceback.
- **`mouse_scroll` did nothing at all on the BSDs.** It matched Windows, then
  macOS, then a literal `["linux", "linux2"]`, so a FreeBSD, OpenBSD, NetBSD or
  DragonFly caller fell off the end of the chain: no backend call, no
  exception, no log line. It asks `platform_id.is_x11_unix()` now, and an
  unrecognised platform raises `AutoControlMouseException` instead of returning
  as though it had scrolled.
- **A recorded timeline replayed nothing.** `replay_timeline`'s dispatch table
  held the `run_sequence` DSL's vocabulary (`press` / `click` / `key`) and the
  recorders emit their own (`key_down` / `mouse_up` / `scroll`), and the two
  were disjoint — so `stop_record_timeline()` fed to `replay_timeline()`, the
  pipeline both the docstrings and the `ac_record_stop_timeline` tool
  prescribe, matched no handler, replayed an empty session, and still returned
  every event as played. The recorder ops dispatch now, and the wheel reads
  `delta` as well as `value` (reading only `value` fell back to the default of
  one notch, so a three-notch scroll down replayed as one notch the other
  way). Affects every platform, not only macOS.
- macOS: recorded mouse coordinates were mirrored vertically. The listener
  read `NSEvent.mouseLocation()`, whose origin is the bottom-left of the
  display, while every replay posts into the top-left space `osx_mouse` uses —
  so a click recorded near the top of the screen replayed near the bottom. It
  now reads `CGEventGetLocation`, which is already in the space the replay
  posts into.
- macOS: modifier keys were not recorded at all. macOS sends no key-down for
  Shift, Control, Option or Command, only a `flagsChanged` event carrying the
  new flag set, so a recording could not say a modifier was held across the
  actions that followed. They are reconstructed from the flags now.
- macOS: `write()` typed a space instead of a backspace, because `"\b"` had
  no route in the macOS key table and fell through to the space fallback.
- macOS: USB enumeration returned `apple_vendor_id` in `vendor_id`, a field
  documented as a four-hex-digit string. A value that is not a hex id is now
  `None`; the device is still listed and `manufacturer` still names the vendor.
- Linux/X11: `window_rect` returned the client area rather than the frame,
  disagreeing with Win32's `GetWindowRect` by the window decorations.
- Linux/X11: `move_window_by_title` configured the client window directly,
  which under a reparenting window manager positions it in the wrong
  coordinate space. It now goes through `_NET_MOVERESIZE_WINDOW`.
- The D-Bus client could not marshal or demarshal signed integers, so any
  protocol using them (AT-SPI extents among them) failed to decode.

- **Wayland: an absolute mouse move through the ydotool fallback counted from
  the wrong origin.** `ydotool mousemove --absolute` emits no absolute event —
  it drives the cursor into the corner the compositor clamps to and then moves
  relative to it, and that corner is the top-left of the output layout rather
  than layout `(0, 0)`. On a layout with a monitor left of the primary one the
  two differ by the layout origin, so `set_position(x, y)` landed a monitor's
  width away from the coordinate the capture path had located. It now
  subtracts `layout_origin()`, the same correction `grab_image` applies.
  Measured against a real wlroots session consuming the real ydotool device
  (`docker/Dockerfile.seat`, the new `seat-verification` job). Layouts whose
  outputs all sit at non-negative positions are unaffected.
- **Wayland: the same call is only pixel-accurate where pointer acceleration
  is off.** The displacement ydotool sends is relative motion, so the
  compositor accelerates it — libinput's default adaptive profile moves the
  cursor exactly twice as far as asked. This cannot be corrected from inside
  the library, because the factor is the compositor's setting; the backend now
  logs the caveat once per process rather than mispositioning in silence.
  Disable acceleration for the ydotoold device (sway: `input type:pointer
  accel_profile flat` and `pointer_accel 0`), or install `liboeffis` so the
  libei path — absolute at the protocol level — is used instead. Once it is
  off, `JE_AUTOCONTROL_WAYLAND_POINTER_ACCEL=flat` silences the warning, and
  `=strict` refuses the move rather than warn about it.

- **The Wayland `xdg-desktop-portal` screen-capture tier could never have
  succeeded.** `org.freedesktop.portal.Screenshot` returns a request handle and
  delivers the image later as a `Response` signal **directed at the connection
  that made the call**; the bus routes a directed message to its destination
  and nowhere else. The implementation listened on a `gdbus monitor`
  subprocess and called from a separate `gdbus` invocation — two connections,
  so the listener was never the addressee. Against a real `dbus-daemon` the
  capture ran out its full 30-second timeout every time. The tier now speaks
  D-Bus itself on a single connection, subscribing to the request path it
  predicts before it calls. No API changed; a path that always failed now
  works.
- **On Wayland, a monitor placed left of or above the primary one made every
  capture path read the wrong pixels.** The compositor lays its outputs out on
  one plane, and that plane starts at a negative coordinate as soon as an
  output sits left of (or above) the origin — a `-1280,0` + `0,0` pair is one
  2560x720 layout whose top-left pixel is at x=-1280. Three places assumed the
  layout began at `(0, 0)`: `screen.size()` returned `max(x + width)`, the
  layout's *right edge* (1280) rather than its width (2560), so everything
  that composes size with a capture — the mss-shaped shim's monitor list,
  `enumerate_monitors`, the recorder, the WebRTC host, the MCP monitor grab —
  asked for half the desktop and called it the whole screen; the region crop
  taken when the capture tier cannot apply one itself (gnome-screenshot,
  spectacle, the portal, an operator's own command) cropped in layout
  coordinates on a layout-origin image, which returns black padding instead of
  the left-hand monitor; and `grab_logical` reported an origin of `(0, 0)`, so
  a template or OCR match found on that monitor was reported 1280 px to the
  right of where it was seen and the click landed on the wrong screen. The
  Wayland backend now publishes `layout_origin()`, `size()` returns the
  bounding box's size, the crop subtracts the origin, and the generic capture
  layer exposes `screen_grabber.backend_layout_origin()` for the paths that
  map a pixel back to a screen coordinate. Verified against a real headless
  sway session laid out that way — the `wayland-verification` job now runs its
  27 checks over both layouts.

- **On Wayland, `set_position` could move nothing at all and report success.**
  libei accepts absolute motion only inside the regions the compositor
  advertises for the pointer, and it discards a point outside every one of
  them without a return code, an event or an error — so the move was lost in
  silence and never reached the ydotool fallback that could have made it.
  Region offsets are `uint32`, so no compositor can advertise a region left of
  or above the origin, while the layout space this project addresses starts at
  `layout_origin()` and goes negative on the same "monitor left of the primary"
  desktop fixed above: on such a layout the input and capture halves named
  different pixels, and the pointer went nowhere rather than to the wrong
  screen. The libei sender now reads the device's regions, sends a covered
  coordinate unchanged, retries an uncovered one normalised by the layout
  origin, and refuses what neither covers so `_select_input` hands the move to
  ydotool. A device that advertises no region is unaffected. Verified against a
  real EIS peer — the `eis-verification` job now runs 20 checks, five of them
  on this coordinate space. The ydotool path's own origin remains unverified
  and unchanged; see `Progress.md`.

- **The Wayland ydotool fallback reported success while sending nothing on
  Debian and Ubuntu.** ydotool 1.0 replaced its entire command line, and every
  argument this backend builds arrived in that release (`mousemove
  --absolute`, `mousemove --wheel`, hex `click` bitmasks, `key CODE:STATE`).
  Debian bookworm, Ubuntu 22.04 and Ubuntu 24.04 all ship 0.1.8 under the name
  `ydotool`, and 0.1.8 exits **0** for those arguments while emitting no
  events at all — including for the ones it rejects with `unrecognised
  option`. Since the backend runs ydotool with `check=True`, nothing raised:
  clicks, keystrokes and cursor moves silently did nothing and every call
  reported success. AutoControl now classifies the installed ydotool once per
  process and raises `AutoControlException` naming the fix instead of
  emitting. **Migration**: install ydotool 1.0+ (Arch, Fedora and Debian
  unstable package it; Debian trixie packages none at all), or set
  `JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11` to drive XWayland. A version the
  probe does not recognise is allowed through, so this cannot block a future
  release. The two `ydotool` install hints no longer suggest `apt install
  ydotool`, which is what produced the broken version.

- **Four clipboard writers never worked on 64-bit Windows**:
  `set_clipboard_files`, `set_clipboard_html`, `set_clipboard_rtf` and
  `set_clipboard_csv` all raised `OverflowError: int too long to convert` on
  every call, and the matching readers failed whenever that format was actually
  present. Each module declared `restype` but not `argtypes`, so ctypes passed
  the pointer-width memory handle as `c_int`. The prototypes and the
  open/alloc/lock dance now live once in
  `je_auto_control/utils/clipboard/win32_clipboard_api.py`, on private `WinDLL`
  handles so the declarations cannot leak into other user32 callers, and
  `rich_clipboard`, `clipboard_rich_formats`, `clipboard_files` and
  `clipboard_formats` all go through it.

- `write` failing a whole string on the first character outside the 192-entry
  virtual-key table — on a US layout that includes `, . / : ? ! _ + @ %` and
  every CJK character, so URLs and non-English text could not be typed at all.
- OCR locating text that the engine split across word boxes (`Save As`,
  `另存新檔`), which previously reported "not found" for text plainly on screen.
- Template matching never finding a target on a second monitor, and returning
  coordinates offset by the physical-vs-logical pixel difference on a mixed-DPI
  desktop (measured ~116 px) and by the virtual-desktop origin.
- Template images failing to load from a path containing non-ASCII characters
  (`cv2.imread` returns `None` there, which surfaced as "could not read image").
- `list_windows` handing back `LP_c_long` pointer objects instead of integer
  hwnds, so `int(hwnd)` raised `ValueError` and a listed window could not be
  used in any follow-up Win32 call. The `EnumWindows` callback declared its
  hwnd as `POINTER(c_int)`; it is now `HWND`, and every Win32 prototype in
  `windows_window_manage` declares `argtypes`/`restype` so a 64-bit handle is
  not truncated to 32 bits. This also un-breaks the `ac_list_windows` MCP tool,
  whose handler called `int(hwnd)`.
- Accessibility listing truncating to `max_results` *before* filtering, so an
  element past the cap could never be found however specific the filter.
- `control_get_value` returning a password field's value when a custom-drawn
  control puts plaintext in ValuePattern instead of masking it.
- The recorder leaking one thread per session: its listener pumped
  `GetMessage` once and `stop_record` never woke it, so the thread stayed
  blocked forever.
- macOS cursor position and omitted-coordinate clicks on Retina / HiDPI
  displays (pixel-vs-point display-height mismatch).
- Remote-desktop relay hang on Linux + CPython 3.14 when one paired peer
  disconnected (a cross-thread `shutdown()` no longer wakes a blocked `recv()`).
- `AC_expect_poll` crashing on a not-ready value instead of continuing to poll;
  `AC_parallel` branch variable-scope isolation; malformed `run_suite` specs now
  report a clean error instead of aborting.
- Windows Interception backend send-to-window click silently no-opping.
- Wayland partial-coordinate `mouse_scroll` raising instead of degrading.
- Action-file save now raises `AutoControlJsonActionException` (not a raw
  `UnicodeEncodeError`) on non-encodable text; non-ASCII USB/IP busid no longer
  kills the client thread; SQLite connections are closed; USB ACL removal is
  case-insensitive.
