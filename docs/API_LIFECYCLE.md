# Public API lifecycle

The supported entry point for new integrations is `je_auto_control.api`.
Everything reachable only through `je_auto_control.utils` is internal unless a
document explicitly says otherwise. The historical top-level package remains
available for compatibility but is not expanded with new integrations.

- Stable API removal requires a deprecation warning and two minor releases.
- Beta API removal requires one release note and one minor release.
- Experimental API may change in any release and must be labelled as such.
- Deprecations state the version introduced, planned removal version, and
  replacement. Use `je_auto_control.utils.deprecation.deprecated`.
- Breaking changes and migrations are recorded in `CHANGELOG.md`.

The project remains pre-1.0. A 1.0 release requires passing stable capability
tests on every claimed platform, documented recovery/diagnostic behavior, and
no unresolved critical security advisories.

## Formats and wire versions

A file or a message that outlives the process that wrote it is an interface
too. Each of the formats below carries its version in the data, and a reader
that meets a version it does not know refuses it instead of guessing.

| Format | Version | Status | What changed, and what an older peer sees |
|---|---|---|---|
| Action journal (`*.jsonl`) | `schema_version` 1 | new, beta | One `start` and one `end` record per executed action, grouped by `run_id`. A line with another `schema_version` raises `JournalFormatError`; a line cut off mid-write is reported as torn, not as an error. Secrets are masked before the line is written. |
| Config-sync wire (`GET` / `PUT /config/{user_id}`) | `version` 2 | **changed** | A `PUT` is now an envelope `{"version": 2, "base_revision", "operation_id", "bucket"}` and is committed only while the stored bucket is at `base_revision`; otherwise `409` with the current revision. A bare bucket (what clients sent before) is answered `428` unless the server runs with `--allow-blind-config-writes`. A `GET` reply gained `revision` and `version`, which older clients ignore. Buckets moved from memory to SQLite (`AC_SIGNALING_CONFIG_DB`). |
| Config-sync entries | version vector per entry | **changed** | An entry written with a device id carries a version vector and merges causally; two changes made apart are both kept as a conflict. Entries without one keep the older rule (the later `last_modified` wins). |
| Action-file signature sidecar (`<file>.sig`) | envelope `version` 2 | new format beside the old one | Version 2 is a JSON envelope `{"version": 2, "algorithm": "ed25519", "key_id", "signature"}`; the private key signs, the public key only verifies. The earlier sidecar (hex HMAC-SHA256) is still written when no key pair is configured. Once a public key is configured an HMAC sidecar is **refused** unless `JE_AUTOCONTROL_ACCEPT_LEGACY_ACTION_SIGNATURES` is set. |
| USB passthrough payloads | optional `request_id` | **changed**, backward compatible | Every viewer request carries a `request_id` (1–64 characters) and the host echoes it in the reply, so a late reply can no longer be handed to the next request. `LIST` and `CLOSE` used to have an empty payload and now send `{"request_id": "..."}`. A host that does not echo ids still works; the viewer then treats a timeout the cautious way. |
| Self-healing evaluation dataset (`*.json`) | `schema_version` 1 | new, beta | Samples, version configs and thresholds for `evaluate_healing_dataset`. Another `schema_version` raises `HealingEvaluationError`. |
| GUI settings (`gui_settings.ini`) | unversioned | new, internal | Theme, text size, navigation panel and window geometry. Not an interface: an unreadable value falls back to its default. |

## Surfaces added in the 2026-10 round

Everything below is reachable from `import je_auto_control`. None of it is in
`je_auto_control.api` yet, so by the first paragraph of this document it is
**beta** unless marked otherwise: usable and tested, and free to change with
one release note.

| Area | Names | Status | Verified by |
|---|---|---|---|
| Capability states | `probe_capabilities`, `BackendContext`, `Capability`, `CapabilitySnapshot`, `CapabilityStatus`, `WindowsFacts`, `MacFacts`, `reset_input_authorisation`, `close_input_session`, `WaylandAuthorisationError` | beta | headless tests on desktops described through `BackendContext`; the probe itself is never a test of the desktop |
| Recording without a hook | `InputStepLog`, `PhysicalRecorder`, `InputDevice`, `InputEvent`, `list_input_devices`, `StopShortcutSession` | beta; `PhysicalRecorder` and `StopShortcutSession` experimental | fakes; no CI job reads a real `/dev/input` device or a real GlobalShortcuts portal |
| Config sync | `config_sync_run` / `_status` / `_resolve` / `_full_resync`, `ConfigStore`, `SyncOutbox`, `SyncAdapter`, `SyncEntry`, `SyncOperation`, `merge_entries`, `sync_assets`, `AssetManifest` | beta | headless tests against a real SQLite store and the FastAPI app in-process |
| Mobile device sessions | `DeviceContext`, `DeviceSession`, `open_device`, `use_device`, `Tap` / `LongPress` / `Swipe` / `Drag` / `Pinch`, `DeviceFrame`, `device_setup_report`, `run_mobile_command`, `mobile_capability_matrix`, `MobileExtension` | experimental | fake `adb` host and fake WebDriverAgent only; **no real device** |
| Healing evaluation | `evaluate_locators`, `evaluate_healing_dataset`, `EvaluationSample`, `HealingComparison`, `template_match_strategy`, `propose_` / `preview_` / `accept_` / `revert_template_revision` | beta | `benchmarks/self_healing/run.py` on drawn frames; no VLM is called |
| Action journal and candidates | `start_action_journal`, `stop_action_journal`, `action_journal_status`, `read_events`, `list_journal_runs`, `generate_candidate_from_log`, `CandidateScript` | beta | headless tests; a candidate is validated by parsing and dry run, never executed |
| MCP tool modes | `ToolMode`, `ToolIndex`, `ToolSummary`, `ToolView`, the `ac_tools_*` tools, `--tool-mode` | beta | in-process server tests and `benchmarks/mcp_discovery.py` |
| Roles | `UserStore`, `AuthorizationContext`, `authorization_scope`, `rbac_add_user` / `_remove_user` / `_set_user_role` / `_rotate_user_token` / `_list_users`, `DeferredOwner`, `capture_owner`, `owner_scope` | beta | headless tests of the REST and MCP HTTP transports |
| Signing | `create_signing_keypair`, `SigningConfig`, `action_signing_config`, `AutoControlSignatureException`, `CryptographyUnavailableError` | beta | headless tests |

"Experimental" here means exactly what it means at the top: it may change in
any release. The mobile row is experimental because nothing in this
repository has driven a real phone, not because the code is unfinished.

## Compatibility notes for callers

- `je_auto_control.execute_action(actions)` takes the action list only.
  `dry_run`, `raise_on_error` and `step_callback` are parameters of
  `je_auto_control.executor.execute_action`.
- A refused or revoked Wayland input consent raises
  `WaylandAuthorisationError` and no longer falls back to `ydotool`. It is
  deliberately not a `RuntimeError`.
- Every framework error still derives from `AutoControlException`; the new
  ones keep a builtin base where callers may already catch one
  (`DeviceError` is a `RuntimeError`, `DeviceTimeoutError` a `TimeoutError`,
  `JournalFormatError` and `JournalImportError` a `ValueError`,
  `AuthorizationError` a `PermissionError`).
- `python -m mypy` holds every module written since v0.0.225 to
  `disallow_untyped_defs` and `disallow_any_generics`; see
  `test/verify/typing_strict_baseline.txt` for the modules that predate that.
