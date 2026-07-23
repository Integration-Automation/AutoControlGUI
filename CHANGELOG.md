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

### Changed

- Releases are prepared from version tags and use PyPI Trusted Publishing.
- The USB/IP server binds `127.0.0.1` by default (least-privilege). Exporting
  the attached device to the LAN now requires an explicit `host="0.0.0.0"`.

### Deprecated

- New integrations should avoid the eager, historical top-level import surface
  and import stable entry points from `je_auto_control.api`.

### Fixed

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
