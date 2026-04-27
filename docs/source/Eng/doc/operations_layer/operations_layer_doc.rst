================================
Operations & Admin Layer
================================

This page documents the operations layer added during AutoControl's
April 2026 hardening cycle (rounds 22–29). Every feature is headless-first
— each ships a Python API, an ``AC_*`` executor command for JSON action
scripts, a REST endpoint when reachable over HTTP, and a Qt GUI tab when
visual interaction makes sense.

The unifying goal: make AutoControl runnable without the desktop GUI, so
it can be deployed as a daemon on remote machines and managed centrally.

.. contents::
   :local:
   :depth: 2


Folder sync (additive mirror)
=============================

Polling-based directory mirror that pushes new and modified files to a
peer via the existing remote-desktop file channel. Sync is *additive
only* — local deletions and renames are not propagated, so engaging
sync mid-edit will never silently destroy remote work.

Headless::

   from pathlib import Path
   from je_auto_control.utils.remote_desktop.file_sync import FolderSyncEngine

   engine = FolderSyncEngine(
       watch_dir=Path("/home/me/notes"),
       sender=lambda local_path, remote_name: my_send(local_path, remote_name),
       poll_interval_s=3.0,
       include_subdirs=False,
   )
   engine.start()
   ...
   engine.stop()

Behaviour:

- Initial snapshot taken on ``start()`` *without* sending — pre-existing
  files are treated as already-synced.
- Each tick scans the directory; files with a newer ``mtime`` than the
  snapshot are sent.
- A failing sender is retried on the next tick (the snapshot only
  records successful sends).
- Local deletions stop being tracked but do not call the sender.

GUI: the WebRTC viewer panel exposes a *Folder sync* group with directory
picker plus Start/Stop buttons.


coturn TURN config bundle
=========================

Generates a deployable coturn configuration so users can self-host TURN
without paying a relay service. Outputs four files:

- ``turnserver.conf`` — coturn configuration
- ``coturn.service`` — systemd unit file
- ``docker-compose.yml`` — single-container deploy (host networking)
- ``README.txt`` — quick reference with ``turn:`` / ``turns:`` URL,
  username, secret

Headless::

   from pathlib import Path
   from je_auto_control.utils.remote_desktop.turn_config import write_bundle

   write_bundle(
       Path("./turn-bundle"),
       realm="turn.example.com",
       user="alice", secret="HUNTER2",
       listen_port=3478, tls_port=5349,
       tls_cert="/etc/letsencrypt/cert.pem",
       tls_key="/etc/letsencrypt/key.pem",
       external_ip="203.0.113.5",
   )

CLI::

   python -m je_auto_control.utils.remote_desktop.turn_config \
       --realm turn.example.com --user alice \
       --secret HUNTER2 \
       --tls-cert /etc/letsencrypt/cert.pem \
       --tls-key /etc/letsencrypt/key.pem \
       --output-dir ./turn-bundle

If ``--secret`` is omitted, a 32-character ``secrets.token_urlsafe`` is
generated.


Hardened REST API
=================

The REST API was rebuilt around three concerns: bearer-token auth, audit
trail, and per-IP rate limiting.

Auth gate
---------

- All endpoints except ``/health`` and ``/dashboard`` require an
  ``Authorization: Bearer <token>`` header.
- Tokens are URL-safe random; ``secrets.compare_digest`` ensures
  constant-time comparison.
- Per-IP token bucket: 120 requests/minute, burst 30.
- Failed-auth tracking: 8 wrong tokens in 60 s → ``locked_out``
  (returns 429); the lockout is per-IP, never global.

Headless::

   from je_auto_control.utils.rest_api import (
       RestApiServer, generate_token,
   )
   server = RestApiServer(host="127.0.0.1", port=9939, enable_audit=True)
   server.start()
   print("Bearer:", server.token)

CLI::

   python -m je_auto_control.utils.rest_api --host 127.0.0.1 --port 9939

Endpoint surface
----------------

Read-only (GET):

- ``/health`` *(unauthenticated)* — liveness probe
- ``/screen_size`` — current screen resolution
- ``/mouse_position`` — current mouse coordinates
- ``/sessions`` — remote-desktop host + viewer status
- ``/commands`` — list of registered ``AC_*`` executor commands
- ``/jobs`` — scheduler job list
- ``/history`` — recent run history rows
- ``/screenshot`` — base64-PNG screenshot
- ``/windows`` — list of OS windows (Windows-only today)
- ``/audit/list`` — recent audit log rows (filters: ``event_type``, ``host_id``, ``limit``)
- ``/audit/verify`` — chain integrity check (see *Audit log hash chain*)
- ``/inspector/recent`` / ``/inspector/summary`` — WebRTC stats
- ``/usb/devices`` — connected USB devices
- ``/diagnose`` — system diagnostics report
- ``/metrics`` — Prometheus exposition (text/plain)
- ``/dashboard`` — web admin UI (HTML; JS bootstraps from sessionStorage token)

Action (POST):

- ``/execute`` — body ``{"actions": [...]}`` — runs an action list
- ``/execute_file`` — body ``{"path": "..."}`` — runs a JSON action file

Executor commands::

   AC_rest_api_start, AC_rest_api_stop, AC_rest_api_status

GUI: *REST API* tab — start/stop, host/port input, audit checkbox,
copy URL / token buttons.


Prometheus metrics
==================

The REST server emits Prometheus exposition v0.0.4 at ``/metrics``.
Counter / gauge families:

- ``autocontrol_rest_uptime_seconds`` — gauge
- ``autocontrol_rest_failed_auth_total`` — counter
- ``autocontrol_rest_audit_rows`` — gauge
- ``autocontrol_active_sessions`` — gauge (host + viewer)
- ``autocontrol_scheduler_jobs`` — gauge
- ``autocontrol_rest_requests_total{method,path,status}`` — counter

Authenticated like every other endpoint — Grafana scrapers must include
the bearer token.

Headless::

   from je_auto_control.utils.rest_api.rest_metrics import RestMetrics
   metrics = RestMetrics()
   metrics.record_request("GET", "/health", 200)
   print(metrics.render())


Multi-host admin console
========================

The admin console manages an address book of remote AutoControl REST
endpoints. Polling is parallel via ``ThreadPoolExecutor``; broadcast
runs the same action list against N hosts and reports per-host results.

Headless::

   from je_auto_control.utils.admin import (
       AdminConsoleClient, default_admin_console,
   )

   client = default_admin_console()
   client.add_host(label="lab-01",
                   base_url="http://10.0.0.5:9939",
                   token="...", tags=["lab"])
   for status in client.poll_all():
       print(status.label, status.healthy, f"{status.latency_ms:.0f} ms")

   results = client.broadcast_execute(
       actions=[["AC_get_mouse_position"]],
   )

Persistence: hosts are saved to ``~/.je_auto_control/admin_hosts.json``
(mode 0600 on POSIX). Reload happens automatically on construction.

Health probe uses ``/sessions`` (an authenticated endpoint), so a host
with the wrong token shows up as unhealthy with an ``HTTP 401`` error
rather than a misleading "reachable but useless" status.

Executor commands::

   AC_admin_add_host, AC_admin_remove_host, AC_admin_list_hosts,
   AC_admin_poll, AC_admin_broadcast_execute

GUI: *Admin Console* tab — register host form, hosts table with
health/latency/jobs columns, broadcast textarea.


Audit log hash chain
====================

The audit log is now tamper-evident: each row stores
``SHA-256(JSON([prev_hash, ts, event_type, host_id, viewer_id, detail]))``,
forming a chain. Editing any past row changes its ``row_hash``, which
no longer matches the next row's ``prev_hash`` — making tampering
visible on the next ``verify_chain()`` call.

Headless::

   from je_auto_control.utils.remote_desktop.audit_log import default_audit_log

   log = default_audit_log()
   log.log("rest_api", host_id="127.0.0.1", detail="GET /health -> ok:200")
   result = log.verify_chain()
   print(result.ok, result.broken_at_id, result.total_rows)

The chain is "trust on first use": rows that existed before the column
was added are backfilled in insertion order at startup.

REST endpoints::

   GET /audit/list?event_type=rest_api&limit=50
   GET /audit/verify

Executor commands::

   AC_audit_log_list, AC_audit_log_verify, AC_audit_log_clear

GUI: *Audit Log* tab — filter form, scrollable table, Verify Chain button
that displays "Chain OK (N rows)" or "Chain broken at row id X of N".


WebRTC packet inspector
=======================

A process-global rolling window of WebRTC ``StatsSnapshot`` samples,
fed by the existing ``StatsPoller`` instances created by the WebRTC
panel. Default capacity 600 samples (~10 minutes at 1 Hz).

Headless::

   from je_auto_control.utils.remote_desktop.webrtc_inspector import (
       default_webrtc_inspector,
   )

   inspector = default_webrtc_inspector()
   summary = inspector.summary()
   recent = inspector.recent(60)

``summary()`` returns per-metric ``last``/``min``/``max``/``avg``/``p95``
for ``rtt_ms``, ``fps``, ``bitrate_kbps``, ``packet_loss_pct``,
``jitter_ms``.

REST endpoints::

   GET /inspector/recent?n=60
   GET /inspector/summary

Executor commands::

   AC_inspector_recent, AC_inspector_summary, AC_inspector_reset

GUI: *Packet Inspector* tab — summary line, per-metric rolling labels,
recent samples table, 1-second auto-refresh.


USB device enumeration
======================

Read-only USB device listing. Tries ``pyusb`` first (cross-platform via
libusb); falls back to platform-specific commands when pyusb is absent.

Backends:

- Windows: ``Get-PnpDevice -PresentOnly -Class USB | ConvertTo-Json``
  (parses VID/PID out of the InstanceId)
- macOS: ``system_profiler -json SPUSBDataType`` (recursive walk)
- Linux: ``/sys/bus/usb/devices`` (sysfs read)

Headless::

   from je_auto_control.utils.usb import list_usb_devices

   result = list_usb_devices()
   print(f"backend={result.backend} count={len(result.devices)}")
   for dev in result.devices:
       print(f"  {dev.vendor_id}:{dev.product_id}  {dev.product}")

REST endpoint::

   GET /usb/devices

Executor command::

   AC_list_usb_devices

GUI: *USB Devices* tab — backend label, devices table (VID/PID/
manufacturer/product/serial/location), refresh button.

Phase 2 (actual USB passthrough) ships in stages — see
:doc:`usb_passthrough_design` for the protocol + backend ABCs and
:doc:`usb_passthrough_operator_guide` for end-to-end usage. The
external security checklist is :doc:`usb_passthrough_security_review`.


USB hotplug events
==================

Polling-based USB add/remove watcher. Diffs successive
:func:`list_usb_devices` snapshots keyed by ``(vendor_id, product_id,
serial, bus_location)``; emits :class:`UsbEvent` records to a callback
and into a bounded sequence-numbered ring buffer (default 500) so late
subscribers can catch up via ``recent_events(since=seq)``.

Headless::

   from je_auto_control.utils.usb import default_usb_watcher

   watcher = default_usb_watcher()
   watcher.start()
   ...
   for event in watcher.recent_events(since=0):
       print(event["seq"], event["kind"], event["device"])

REST endpoint::

   GET /usb/events?since=<seq>&limit=<n>

Executor commands::

   AC_usb_watch_start, AC_usb_watch_stop, AC_usb_recent_events

GUI: *USB Devices* tab now has an *Auto-refresh + watch hotplug*
checkbox; ticking it starts the singleton watcher and shows the
last few events.


System diagnostics
==================

A "is everything OK?" probe across AutoControl's subsystems. Each check
is a small function returning a ``Check(name, ok, severity, detail)``;
the runner catches per-check exceptions so one broken probe never
poisons the rest.

Bundled checks:

- ``platform`` — OS + Python version
- ``optional_deps`` — inventory of optional modules (aiortc, av, pyusb,
  pyaudio, pytesseract, cv2, PySide6) with available/missing breakdown
- ``executor`` — count of registered ``AC_*`` commands
- ``audit_chain`` — chain integrity (uses ``verify_chain()``)
- ``screenshot`` — captures a real screen image
- ``mouse`` — reads current mouse position
- ``disk_space`` — free space in user home (warn <1 GB, error <100 MB)
- ``rest_api`` — registry singleton state

Headless::

   from je_auto_control.utils.diagnostics import run_diagnostics

   report = run_diagnostics()
   for check in report.checks:
       print(f"[{check.severity}] {check.name}: {check.detail}")
   print("ok:", report.ok)

CLI::

   python -m je_auto_control.utils.diagnostics
   # exit code 0 if all green, 1 otherwise

REST endpoint::

   GET /diagnose

Executor command::

   AC_diagnose

GUI: *Diagnostics* tab — Run button, severity-colored results table,
summary line.


Web admin dashboard
===================

A single-page browser UI hanging off the REST API. Vanilla JavaScript
(no build step) — the page is a thin shell at ``/dashboard`` that
prompts the user for the bearer token, caches it in ``sessionStorage``,
and polls the existing endpoints every 5 seconds.

Panels: diagnostics, sessions, inspector, USB devices, audit log tail.

The page itself is unauthenticated (just static HTML/CSS/JS); every
data call goes through the auth-gated endpoints with the
user-provided token. ``sessionStorage`` clears on tab close so the
token doesn't survive a browser restart.

Path-traversal protection: the asset loader matches against
``^[A-Za-z0-9_][A-Za-z0-9._-]*$`` and verifies ``Path.resolve()``
stays under the dashboard directory. ``..`` and URL-encoded variants
both return 404.

Open ``http://<host>:9939/dashboard`` in any browser, paste the bearer
token from the *REST API* tab, and you have a live ops view that works
on phones too.


OpenAPI 3.1 + Swagger UI
========================

The REST server exposes its full route table as an OpenAPI 3.1
document so external tooling (client SDK generators, API explorers,
contract tests) can consume it directly.

REST endpoints::

   GET /openapi.json    — the spec, auth-gated
   GET /docs            — Swagger UI shell, unauthenticated
                          (the JS prompts for the bearer token and
                           injects it into try-it-out requests)

Headless::

   from je_auto_control.utils.rest_api.rest_openapi import (
       build_openapi_spec, known_endpoints,
   )
   spec = build_openapi_spec(server_url="http://my-host:9939")
   for method, path in known_endpoints():
       print(method, path)

The metadata mapping that drives the spec lives in
``rest_openapi._ENDPOINT_METADATA`` next to the generator. A drift
test in CI (``test_every_route_has_metadata``) refuses to merge new
``_GET_ROUTES`` / ``_POST_ROUTES`` entries that don't have matching
metadata.

Each endpoint declares its summary, query parameters, request body
schema (POSTs), expected responses, and inherits the global
``BearerAuth`` security scheme — public paths (``/health``,
``/dashboard``, ``/docs``) override with explicit ``security: []``.


Configuration bundle
====================

Single-file JSON export / import of the user-config directory under
``~/.je_auto_control/``. The allowlist covers the eight files that
encode actual operator preferences (admin hosts, address book,
trusted viewers, known hosts, host service, plus the persistent
``remote_host_id``, ``viewer_id`` and ``host_fingerprint``). The
audit log (``audit.db``) is intentionally NOT in the allowlist —
restoring it from a bundle would destroy the tamper-evident chain.

Headless::

   from je_auto_control.utils.config_bundle import (
       export_config_bundle, import_config_bundle,
   )

   bundle = export_config_bundle()
   # ... ship to the new machine ...
   report = import_config_bundle(bundle)
   print(report.written, report.skipped, report.backups)

Import is non-destructive: anything we are about to overwrite is
first renamed to ``<name>.bak.<unix_ts>``. Bad versions, unknown
filenames and path-traversal attempts are rejected; format
mismatches between the bundle and the allowlist (e.g. a ``text``
entry where the allowlist expects ``json``) are skipped.

CLI::

   python -m je_auto_control.utils.config_bundle export <file>
   python -m je_auto_control.utils.config_bundle import <file>
                                                       [--dry-run]

REST::

   POST /config/export    — returns the bundle inline as the response body
   POST /config/import    — body IS the bundle dict

Executor commands::

   AC_config_export, AC_config_import

GUI: *Export Config* / *Import Config* buttons on the REST API tab,
both with file dialogs and overwrite-confirmation dialogs.
