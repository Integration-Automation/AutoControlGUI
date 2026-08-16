# Changelog

This file records user-visible compatibility changes. Detailed development
notes remain in `WHATS_NEW.md`.

The format follows Keep a Changelog. Until 1.0, breaking changes are permitted
only when documented here with a migration path.

## Unreleased

### Added

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
- `utils/url_canon` reaches its delivery surfaces: `canonicalize_url`,
  `normalize_url`, `urls_equal`, `build_query` and `parse_query` are exported
  from the facade, with `AC_canonicalize_url` / `AC_normalize_url` /
  `AC_urls_equal`, the matching `ac_*` MCP tools, and three Script Builder
  specs. The module and its tests already existed; only the wiring is new.

### Removed

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

- New integrations should avoid the eager, historical top-level import surface
  and import stable entry points from `je_auto_control.api`.

### Fixed

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
