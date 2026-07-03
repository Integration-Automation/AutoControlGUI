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

### Deprecated

- New integrations should avoid the eager, historical top-level import surface
  and import stable entry points from `je_auto_control.api`.
