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

## What 1.0.0 promises

1.0.0 (2026-10-09) is the first release under semantic versioning. The
promise covers the **stable** surface only: `je_auto_control.api`, and the
capabilities `docs/CAPABILITY_MATRIX.md` marks stable. From here a breaking
change to that surface needs a new major version and the deprecation window
above. Beta and experimental surfaces keep the rules above and may change in a
minor release with a release note.

The bar for 1.0 was: stable capability tests passing on every platform the
matrix claims, documented recovery and diagnostic behavior, and no unresolved
critical security advisory. As released:

- The stable rows of the matrix are run by CI on Windows, Linux X11 and Linux
  Wayland. On macOS the mouse / keyboard / screenshot row is still
  "implementation": the stable-API suite passes on the macOS runner, but no
  job drives a real pointer there. Treat macOS input as beta until that row
  says CI.
- Recovery and diagnostics are `create_failure_bundle`, the trace and report
  writers and the action journal, described in the README and `docs/source`.
- GitHub reported no open Dependabot alert and no open repository security
  advisory on the day of the release.

What has not been verified on real hardware (a Mac, a phone, a Wayland desktop
session, USB devices) is listed in `Progress.md`; none of it is in the stable
surface.

## Formats and wire versions

A file or a message that outlives the process that wrote it is an interface
too. Each of the formats below carries its version in the data, and a reader
that meets a version it does not know refuses it instead of guessing.

| Format | Version | Status | What changed, and what an older peer sees |
|---|---|---|---|
| Action journal (`*.jsonl`) | `schema_version` 1 | new, beta | One `start` and one `end` record per executed action, grouped by `run_id`. A line with another `schema_version` raises `JournalFormatError`; a line cut off mid-write is reported as torn, not as an error. Secrets are masked before the line is written. |
| Config-sync wire (`GET` / `PUT /config/{user_id}`) | `version` 2 | **changed** | A `PUT` is now an envelope `{"version": 2, "base_revision", "operation_id", "bucket"}` and is committed only while the stored bucket is at `base_revision`; otherwise `409` with the current revision. A repeated `operation_id` with a *different* bucket or base revision is `409` with `"code": "operation_mismatch"` (it used to be answered as committed); a client that does not know the code treats it as an ordinary revision conflict. A bare bucket (what clients sent before) is answered `428` unless the server runs with `--allow-blind-config-writes`. A `GET` reply gained `revision` and `version`, which older clients ignore. Buckets moved from memory to SQLite (`AC_SIGNALING_CONFIG_DB`). |
| Config-sync assets (`/blobs/{user_id}/{sha256}`) | unversioned, additive | new | `PUT` / `GET` / `HEAD` / `DELETE` of content-addressed blobs per account on the signaling server, and `GET /blobs/{user_id}` for usage; same shared secret as `/config`, a per-blob cap (`413`, default 16 MiB) and a per-account quota (`507`, default 256 MiB). The `/config` wire stays version 2. A server from before these routes answers `404` / `405`, which `HttpAssetTransport` reports as "the server does not serve /blobs"; a client that does not use them is unaffected. |
| Config-sync entries | version vector per entry | **changed** | An entry carries a version vector and merges causally; two changes made apart are both kept as a conflict. `ConfigBucket.upsert` / `remove` version every entry they write (`origin` defaults to this machine's device id), so the value is stored under `value` -- read it with `bucket.values(section)`. Flat entries already in a bucket, or written with `versioned=False`, keep the older rule (the later `last_modified` wins). `ConfigSyncClient.sync` records its device under `peers`. |
| Action-file signature sidecar (`<file>.sig`) | envelope `version` 2 | new format beside the old one | Version 2 is a JSON envelope `{"version": 2, "algorithm": "ed25519", "key_id", "signature"}`; the private key signs, the public key only verifies. The earlier sidecar (hex HMAC-SHA256) is still written when no key pair is configured. Once a public key is configured an HMAC sidecar is **refused** unless `JE_AUTOCONTROL_ACCEPT_LEGACY_ACTION_SIGNATURES` is set. |
| USB passthrough payloads | optional `request_id` | **changed**, backward compatible | Every viewer request carries a `request_id` (1–64 characters) and the host echoes it in the reply, so a late reply can no longer be handed to the next request. `LIST` and `CLOSE` used to have an empty payload and now send `{"request_id": "..."}`. A host that does not echo ids still works; the viewer then treats a timeout the cautious way. |
| USB passthrough ACL (`usb_acl.json`) | `version` 1, signature embedded | **changed**, reads the old layout | The HMAC-SHA256 signature moved from the sidecar `usb_acl.json.sig` into the file, as `"signature": {"algorithm": "hmac-sha256", "value"}` over the other fields in canonical JSON, so data and signature are replaced in one rename. A two-file ACL still loads and is rewritten as one file (the `.sig` is removed) on the next save. **An older version cannot read the new file**: it finds a key without a sidecar and denies everything until the ACL is re-created there. Changes also take `usb_acl.json.lock`; one that cannot get it within ten seconds raises `UsbAclBusyError`. |
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

- `je_auto_control.execute_action(actions, *, raise_on_error=False,
  dry_run=False, step_callback=None, result_callback=None)` takes the same
  keyword-only options as `je_auto_control.executor.execute_action`.
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
