# Changelog

This file records user-visible compatibility changes. Detailed development
notes are recorded in `docs/updates/` (index: `docs/updates/README.md`).

The format follows Keep a Changelog. Until 1.0, breaking changes are permitted
only when documented here with a migration path.

New entries go under `## Unreleased`. The version bump on `main` is automated
and does not touch this file, so after a release tag appears, move the entries
it shipped into a `## [x.y.z] - date` section of their own; the tag's
`CHANGELOG.md` shows which ones those are (`git show vX.Y.Z:CHANGELOG.md`).

## Unreleased

### Added

- **`approval_gate(db=None)`.** The approval gate the `AC_approval_*`
  commands use: file-backed with `db`, otherwise one per process.

- **`adaptive_mean` / `adaptive_gaussian` preprocessing steps.** They take
  `block_size` / `c`, which no step used before.

- **`SoftAssertionsFailed`.** The exception `SoftAssertions.assert_all`
  raises; exported from the package.

- **State-machine `if_image_found` guard.** Fires once the template is on
  screen (`"welcome.png"` or `{"image": ..., "detect_threshold": ...}`).
  Other `if_*` keys, which used to fire unconditionally, now raise
  `StateMachineError`.

- **`WorkQueue.get_next(stale_after_s=...)`** (and the same optional
  argument on `AC_queue_next` / `ac_queue_next`) reclaims an item a crashed
  performer left in progress for that many seconds.

- **`ac_rrule_next`, `ac_rrule_occurrences` and `ac_format_date` now declare
  the string format they parse.** Their `dtstart` / `now` / `value` properties
  carry `"format": "date-time"` (or `"date"`) in the tool's input schema, which
  the descriptions already said in prose and the schema did not. A client
  generating values from the schema alone used to produce a plain string and
  get a `ValueError` out of `datetime.fromisoformat`.

### Changed

- **`replay_timeline` / `run_sequence` refuse unknown ops and bad speeds.**
  An unknown op raises instead of being skipped, and `speed` must be a
  positive number.

- **`WorkQueue.complete` / `fail` require an `in_progress` item.** An unknown
  id or an item in another state raises, so finished work is never requeued
  and a stale performer cannot overwrite a newer outcome.

- **`AgentTrace.to_otel` returns OTLP/JSON spans** (trace and span ids,
  nanosecond times, integer enums, typed attributes) instead of flat dicts
  with `duration_s`. Cost records refuse negative token counts.

- **`AssetStore.set` validates the type and value** it is given, and a
  string `tags` argument is one tag, not a list of letters.

- **Plugins cannot replace built-in commands by default.**
  `register_plugin_commands` and `load_plugins` skip (and log) a name that
  already belongs to a built-in or user command; pass `allow_override=True`
  to replace one deliberately.

- **Impossible rate-limit requests raise.** `TokenBucket` and
  `SlidingWindowLimiter` refuse `n <= 0` or above capacity / limit, and
  `CredentialBroker.lease` refuses a TTL that is not a finite positive number.

- **Pseudo-localization padding counts visible text only**, and
  `check_catalog` compares printf conversions and argument names rather
  than whole ICU blocks.

- **Colour-match scores are RMS colour distance.** `match_color` scores are
  `1 -` the root-mean-square HSV distance, hue compared round the colour
  wheel; `min_score` thresholds tuned on the old metric may need adjusting.
  `AC_image_hash` refuses an unknown `algo`, `hamming_distance` refuses
  hashes of different sizes, and `upscale` refuses a non-positive scale.

- **A failed soft-assert batch is an assertion failure.** It raises
  `SoftAssertionsFailed` (an `AutoControlAssertionException` and still an
  `AutoControlActionException`), so suites score it *failed* and lenient runs
  no longer swallow it.

- **`raise_on_error=True` reaches into nested bodies.** Loops, branches and
  macros run by a strict list are strict too, so a failure inside them
  raises instead of being recorded; lenient runs are unchanged.

- **JSONPath refuses what it cannot read.** `json_query` raises `ValueError`
  for an unsupported filter, an unterminated `[` or a stray character (an
  unsupported filter used to match every element). Filters take nested
  fields (`@.a.b`) and existence tests (`[?(@.k)]`), `true` no longer equals
  `1`, and a bare key may contain `-`.

- **More MCP tools are destructive.** Tools that run action lists or code,
  send input, delete data, send data off the machine or loosen a security
  control carry `destructiveHint: true`, so
  `JE_AUTOCONTROL_MCP_CONFIRM_DESTRUCTIVE=1` asks before them.
  `ac_export_sarif`, `ac_compliance_report` and `ac_assert_visual` are no
  longer read-only. A `tools/call` argument the schema does not declare is
  refused with `-32602`.

- **Secret-key matching is by word.** `scan_secrets` and `redact_config` no
  longer treat keys that merely contain `pass` or `token` (`bypass_proxy`,
  `tokenizer`) as secrets, and now do treat `apiKey`, `cookie`, `sessionId`
  and `Authorization` as secrets. A redaction bounding box with no known
  coordinate keys raises `ValueError`.

- **An empty window title is an error.** `find_window`, `focus_window`,
  `close_window_by_title` and the other title lookups raise
  `AutoControlActionException` for a blank or non-string title; `""` used to
  match every window.

- **`je_auto_control run` exits 1 when any action failed.** It used to exit
  0 whenever the file loaded. Migration: a pipeline that relied on the old
  status can ignore it (`|| true`).

- **Chat-ops `/screenshot` takes a file name, not a path.** The PNG is
  written into the router context's `screenshot_dir` (default: a
  `je_auto_control_chatops` folder in the temp directory); anyone in the
  channel could previously choose any path. Migration: set `screenshot_dir`.

- **`AC_shell_to_var` on Windows.** A string command is passed to
  `CreateProcess` as written; quoted arguments used to arrive with their
  quotes still on. Output is decoded with the new `encoding` argument,
  defaulting to the locale's encoding rather than always UTF-8. Migration:
  pass `"encoding": "utf-8"` for a program that writes UTF-8.

- **Passphrase-encrypted action files are salted.** `encrypt_action_file`
  with a passphrase now derives the key with scrypt and a random per-file
  salt, and writes `ACENC1:` + salt + token; it used one unsalted SHA-256.
  Older files still decrypt. Migration: none, but a file written by this
  version cannot be decrypted by an older one.

- **`max_runs` must be at least 1.** `Scheduler.add_job` and
  `add_cron_job` raise `ValueError` for `max_runs=0` or below, which used to
  run the job once. Migration: pass `max_runs=1`.

- **Importing the package no longer sets the root logger to DEBUG.** A
  library must not reconfigure its host's logging, and that one line sent
  every third-party logger's DEBUG records to whatever handlers the host
  application had configured. `autocontrol_logger` now carries the DEBUG
  level itself, so this package's own records are unchanged. Migration: a
  program that relied on the side effect should call
  `logging.getLogger().setLevel(logging.DEBUG)` itself.

- **Per-user state paths are resolved when used, not at import.** Nine
  defaults under `~/.je_auto_control/` (the action signing and encryption
  keys, the host fingerprint and known hosts, the host service config, the
  WebRTC inbox, and the A/B locator, cost and self-healing logs) were fixed
  when their module was imported, so setting `HOME` / `USERPROFILE`
  afterwards had no effect on them. The class attributes
  `ABStore.DEFAULT_PATH`, `CostStore.DEFAULT_PATH` and
  `HealEventLog.DEFAULT_PATH` are replaced by the functions
  `default_stats_path()`, `default_cost_log_path()` and
  `default_heal_log_path()` in the same modules. Migration: call the
  function where the attribute was read.

- **The log file moved out of the current directory.** Importing the package
  opened `AutoControlGUI.log` relative to the cwd, so every process that
  imported it — including every pytest run on a machine where it is installed,
  through the `pytest11` plugin — left a log wherever it started. The file is
  now `~/.je_auto_control/logs/AutoControlGUI.log`, or whatever
  `JE_AUTOCONTROL_LOG_FILE` names when the file is first opened, so a
  `conftest.py` can still redirect it after the plugin imported the package
  (`os.devnull` turns it off). Because every
  process shares it, lines carry the process id (`time | pid | logger | level
  | message`), and instead of growing without limit it is moved to `.1` once
  past 10 MB, at the moment a process opens it. The file is opened on the
  first record rather than at import, and the `Load Windows Setting` /
  `Load Linux x11 Setting` / `Load Linux Wayland Setting` / `Load MacOS
  Setting` lines every import used to log are gone, so importing the package
  writes no file. A file that cannot be opened (read-only home or cwd) is
  replaced by `os.devnull` with one `RuntimeWarning`; it used to make
  `import je_auto_control` fail.
  Migration: to keep the old location, set
  `JE_AUTOCONTROL_LOG_FILE=AutoControlGUI.log`; changing the working
  directory before the import no longer redirects the file.

### Security

- **MCP over HTTP: a web page could drive the machine, and one session could
  confirm another's destructive call.** With no token configured (the default)
  the server accepted cross-site browser requests — a `text/plain` POST needs
  no CORS preflight — so any page the user opened could run tools; it now
  refuses a non-loopback `Origin`, and a non-loopback `Host` when bound to
  loopback (DNS rebinding). `JE_AUTOCONTROL_MCP_ALLOWED_ORIGINS` admits
  specific browser origins. Replies to server-sent prompts were matched by a
  sequential id alone, so any client could accept a confirmation shown to
  another; they are now bound to the session the prompt went to and the ids
  are random. With `JE_AUTOCONTROL_MCP_CONFIRM_DESTRUCTIVE=1`, a destructive
  call that had no stream to ask on ran unconfirmed; it is refused. A
  non-ASCII bearer token crashed the request thread in both the MCP and REST
  servers (never counted toward lockout); it is refused.

- **USB passthrough: three ways a viewer got past the ACL.** Vendor and
  product ids were compared as strings but parsed by the backend with
  `int(x, 16)`, so `0x1050`, `01050` or `10_50` missed a `1050` deny rule and
  opened the device anyway; ids are now normalised to four lowercase hex digits
  (an optional `0x` prefix is accepted, anything else is refused). A viewer
  that omitted the serial skipped rules written for one serial and got
  whichever matching device the backend found first; that is refused when the
  ACL has a serial rule for the device. The WinUSB backend logged a requested
  serial and ignored it; it now refuses to open by serial. Transfer `length`
  and `timeout_ms` from the wire are bounded (control 0–65535, bulk/interrupt
  up to 1 MiB, timeout up to 60 s), where a single request could make the host
  allocate a gigabyte.

- **A WebRTC viewer could be approved without ever sending the token.** The
  public `approve_pending_viewer` guard read `not pending and authenticated`,
  so for a session whose viewer had sent nothing both were false and the
  approval went through, cancelling the auth deadline and accepting input.
  Only a viewer that presented the token and is waiting on the user can be
  approved now; the token is compared with `hmac.compare_digest` instead of
  `!=`, which leaked how many leading characters matched.

- **The `pdf` extra now requires `pypdf>=6.16.1`** (was `>=4.0`).
  `extract_pdf_text`, `pdf_metadata` and `assert_pdf_text` open whatever PDF
  they are given, and every pypdf before 6.16.1 can be driven into an
  infinite loop or unbounded memory by a malformed file (unterminated inline
  images, repeated bad cross-reference entries, large `/ToUnicode` streams or
  CID width ranges, `TreeObject.insert_child`, outlines, XForm objects).
  Migration: `pip install -U "je_auto_control[pdf]"`.
- **`requirements.txt` states `pillow>=12.3.0` directly.** It already
  resolved 12.3.0 through the `je_auto_control>=0.0.216` floor; the direct
  line is for the dependency graph, which still reported Pillow 12.2.0 for
  this file from before that floor existed.
- **`uv.lock` moves anyio 4.13.0 → 4.14.2, cryptography 49.0.0 → 50.0.1 and
  pypdf 6.13.3 → 6.19.0.** anyio (through `starlette`, `[signaling]` extra)
  fixes a TLS host-name encoding flaw that allowed certificate spoofing.
  cryptography 50 fixes a PKCS#7 EnvelopedData decryption oracle; this
  package does no PKCS#7 decryption, so the `>=48.0.1` floor is unchanged.

### Fixed

- **Replays happen where they were recorded and never leave keys held.**
  Recorded presses, releases and scrolls move to their recorded position;
  recording gaps keep their total length; a failing step in `run_sequence`,
  `replay_timeline`, `tween_drag` or `drag_path` releases held keys and
  buttons. Windows accepts `ctrl` and every platform accepts `left` /
  `right` / `middle` as button names.

- **Sagas roll back.** `run_saga` / `AC_run_saga` ran steps leniently, so a
  failing step was never noticed and nothing was compensated; a compensation
  that raises is reported in `compensation_errors`. One failing device no
  longer aborts the device matrix, a DAG node raising any exception fails
  that node, and an observer rule removed mid-poll no longer fires.

- **Metrics, SARIF, SBOM and version checks follow their specs.** Labelled
  Prometheus metrics no longer render a bogus unlabelled series, partial
  label sets and non-ASCII names are refused and HELP text is escaped. SARIF
  levels are normalised, lint issues point at the right 1-based line and
  file locations are URIs. SBOM purls are normalised and percent-encoded.
  The vulnerability scan orders PEP 440 and SemVer pre-releases before their
  release. W3C multi-tenant `tracestate` keys are kept. Step videos resize
  mismatched frames, fail on an unwritable path and leave the caller's frame
  untouched.

- **Stores keep what they are given.** Two skill libraries or element
  repositories on one file no longer lose each other's saves (a corrupt file
  still raises rather than being erased); asset commands without `db` share
  one store; a config-bundle entry without content no longer empties its
  file, and imported files are written 0600; agent memory recalls non-ASCII
  words; action files with a UTF-8 BOM load.

- **Plugins load reliably.** One plugin file that fails to import no longer
  stops the rest of its directory, `@dataclass` plugins load, a non-function
  entry-point value is skipped instead of aborting discovery half-way, and
  the MCP plugin watcher keeps a tool another file still defines.

- **Approvals and leases enforce what they promise.** Approval commands
  without `db` share one gate (a token was forgotten between commands), an
  anonymous approver is refused, and a lease TTL of NaN or infinity is
  rejected instead of never expiring.
- **Retry, rate-limit and breaker edge cases.** Backoff caps huge attempt
  numbers instead of overflowing, `RetryPolicy` caps its first sleep, the
  sliding-window wait is long enough, asctime `Retry-After` dates are GMT,
  the loop guard reports the longest stuck pattern, re-created CAS keys never
  reuse a version, an interrupted half-open trial no longer jams the
  breaker, and idempotency claims are atomic with the TTL starting at
  completion.

- **Text and clipboard helpers handle real-world input.** Long
  near-identical strings fuzzy-match again; RTF round-trips characters
  beyond the BMP, lone CRs and Word's fallback escapes; a file-drop list
  with an empty path is refused and parsing stops at its terminator;
  pseudo-localization keeps printf, HTML and ICU placeholders; `slugify`
  inserts the separator literally; a null CSV cell is empty.

- **Image utilities see the colours and files they are given.** Grayscale
  no longer swaps red and blue for PIL images and screen grabs, palette
  images are read by colour, deskew works on dark themes, and image paths
  may contain non-ASCII characters. A red glyph can be colour-matched, colour
  regions accept any PIL mode, a golden of another size is a mismatch rather
  than an error, and zero-area elements get no mark.
- **An approval `extension` cannot leave `approvals_dir`.**

- **Test reports and suites count what happened.** A setup failure is
  counted in the JUnit totals and reported to Allure; `assert_http` scores a
  read timeout or dropped connection as a failed assertion instead of
  crashing; `assert_eventually` refuses a NaN timeout (an endless loop); one
  malformed case or quarantine entry no longer aborts the suite; string tags
  are one tag; runs with equal timestamps list newest first;
  `critical_steps(top=0)` is empty.

- **Failures inside nested blocks reach `AC_try`, `AC_retry` and strict
  callers.** A failure inside an `AC_loop`, `AC_if_*` branch or macro was
  swallowed at the block boundary. `AC_try` / `AC_retry` now also catch
  arithmetic and lookup errors and let the macro depth limit reach the
  top-level record; a planned `AC_break` is recorded instead of raised.
- **A variable's value is never expanded as a placeholder.** Commands that
  run a nested action list (`AC_execute_action`, `AC_circuit_call`,
  `AC_run_saga`, ...) expanded it twice, so a value containing
  `${secrets.NAME}` was resolved from the vault.

- **VEX no longer suppresses findings it does not cover.** `apply_vex`
  matches products by package name instead of substring, honours the
  statement's aliases, and lets a later statement supersede an earlier one.
- **Parsing fixes for `.env`, data sources and HTTP headers.** Quoted `.env`
  values drop a trailing comment and may span lines; `dump_dotenv` output
  parses back unchanged. CSV/JSON data sources skip a UTF-8 BOM. A past
  cookie `Expires` deletes the cookie and a nameless cookie is ignored;
  quoted `Cache-Control` and `Link` parameters stay whole; `rel` is
  case-insensitive; SSE handles a `\r\n` split across chunks and a BOM.

- **JSON Patch, JSONPath and unified diffs follow their specs.** JSON Patch
  `add` accepts an index equal to the array length and no longer shares its
  value with the patch; `move` checks its source. `apply_unified` places
  `-N,0` insertion hunks correctly, keeps body lines that start with `---` /
  `+++` and skips `\ No newline` markers. `three_way_merge` reports two
  insertions at one point as a conflict and applies an identical change once.

- **MCP read-only mode and the confirmation gate hold.** `ac_bulkhead_run`
  and `ac_run_chaos` no longer run action lists in read-only mode; file
  writers and `ac_assert_http` with a mutating method are out of it; read-only
  tools no longer create a database at a missing `db` path; `resources/read`
  serves only the `*.json` files `resources/list` shows.

- **Secrets stay out of reports, bundles and logs.** Secret keys are matched
  by word (`apiKey`, `db_password`, `sessionId` count; `tokenizer` does not);
  list and tuple items and numbers under a secret key are checked; JWTs and
  credentials URLs are found; free-text redaction masks prefixed keys,
  Basic/Token/Digest `Authorization` and URL passwords. Failure bundles mask
  `AC_secret_*` arguments, re-raise the block's own error when the bundle
  cannot be written, and drop a truncated log's partial first line.
  Screenshot redaction reads `x/y/width/height` boxes and handles palette,
  grayscale and bilevel images.

- **Accessibility, OCR and window lookups match what was asked.** A blank
  `contains` name no longer matches every element; a blank window title is
  refused instead of matching (and closing) the first window; Linux
  single-control lookups honour `window_title`; saving and restoring a window
  layout no longer reads or moves the wrong window when titles overlap or
  repeat; `show_window` no longer foregrounds a window it was told to
  minimise or show without activating; `wait_for_window` / `wait_for_text`
  with `timeout=0` look once; OCR text matching normalises Unicode.

- **Android input cannot run shell commands on the device.** Text typed with
  `AC_android_text` is shell-quoted, and `AC_android_key` accepts only key
  names and codes; `$(...)`, quotes or `;` in either used to reach the
  device shell.
- **Android and iOS device errors are contained.** uiautomator2, adbutils
  and facebook-wda errors (no device, several devices, an invalid session)
  are raised as `UIAutomatorUnavailableError` / `IOSUnavailableError`
  instead of aborting the rest of a script.

- **Image location is accurate.** `locate_image_center` / `locate_and_click`
  return the best-scoring match instead of the first position over the
  threshold (which was a few pixels off), an identical template now matches
  at the default threshold of 1.0, and `locate_all_image(draw_image=True)`
  works. A missing template file or a threshold outside 0..1 raises
  `ImageNotFoundException` naming the problem.
- **Mouse and keyboard input.** Scrolling at a point on a secondary monitor
  reaches it instead of the primary monitor's edge; a coordinate that is not
  a number or is out of range raises `AutoControlMouseException` instead of
  moving somewhere else; on Windows a keycode past 16 bits is refused instead
  of pressing a different key.

- **Computer-use agent actions work.** Clicks, double and triple clicks,
  drags, waits and held keys were translated into calls the executor could
  not make, so each failed as a step error; they now map to real commands.
- **Agent backends run only the tools they offered.** A model reply naming
  any other `AC_*` command (a shell command, for instance) raises
  `AgentBackendError` instead of executing; unparsable or non-object OpenAI
  arguments raise instead of running the tool with `{}`; computer-use
  coordinates are clamped to the display.
- **VLM location.** Provider errors (rate limit, timeout) are handled like
  other request failures instead of escaping, and a point outside the
  requested region is "not found" instead of clicked.

- **Circuit breaker, config sync and ACME.** A half-open circuit breaker
  admits one trial call at a time instead of every concurrent caller, and is
  safe to share between threads. Config sync rejects a malformed server reply
  and reports a dropped connection as `ConfigSyncError`; the ACME client
  reports an unreachable CA as `AcmeError` and a bad CSR as `JwsError`; and
  `renewal_due` accepts a naive `now`.

- **DAG, state machine, recurrence rules and suites.** A DAG node whose
  actions fail is failed (its dependants are skipped), and a slow node no
  longer holds back unrelated ready nodes. State-machine `after` guards wait
  for their timer, counted from state entry, and reaching the final state on
  the last allowed step succeeds. YEARLY RRULEs without BYMONTH cover the
  whole year as RFC 5545 specifies, a rule that can never match ends instead
  of overflowing, and invalid INTERVAL / COUNT / BYMONTH / BYMONTHDAY values
  are rejected. A data-driven suite no longer leaves its row variable set,
  and an `OverflowError` or `ZeroDivisionError` from an action is recorded
  instead of aborting the script.

- **Remote desktop keeps serving after bad input.** A malformed INPUT
  message or WebSocket frame no longer kills the host's receive thread while
  its viewer keeps a client slot, nor the viewer's thread without an error
  callback; a slow or silent peer no longer blocks other viewers from
  connecting (each connection is handshaken on its own thread); and a
  signaling timeout or hang-up is reported as `SignalingError`.

- **Generated code cannot run what an action file smuggles in.** Codegen
  emits a parameter as a keyword argument only when its name is a plain
  identifier, and the Robot target carries the actions base64-encoded.
  Pytest code generated with `failure_bundle=True` now runs (it imported the
  wrong module as `ac`).
- **USB/IP, TLS keys, signaling and relay.** A USB/IP client can only send
  URBs to the device it imported; TLS private keys are written atomically and
  0600 from creation; the signaling server compares its secret in constant
  time and caps live sessions (503 when full); and the relay frees the slot
  of a parked peer that disconnected.

- **Approval gate, asset store and locator-repair store across processes.**
  Each change re-reads the file under a lock file, so processes sharing it no
  longer overwrite each other; an approval request can be decided only once.

- **Recording and hotkeys.** A recording that cannot start no longer
  replaces the output file with `[]`; starting a second recording stops the
  first input hook instead of leaking it. Hotkeys on punctuation keys
  (`ctrl+.`, `ctrl+[`) register those keys rather than Delete or the Windows
  key; a combo Windows cannot register is refused by `bind` and no longer
  retried 20 times a second; and an error in the run history or an injected
  executor no longer ends the hotkey listener.
- **Legacy `python -m je_auto_control`.** A missing or invalid action file
  is reported as a log line instead of a traceback (the exit status was
  already 1), and a `-d` path that is not a directory is an error.

- **JSON-file stores.** The flaky-test quarantine, the remote-desktop trust
  list and known hosts, and the RBAC user store are replaced atomically
  (readers never see a partial file) and load empty instead of raising when
  the file is not UTF-8 or has the wrong shape. A failed first read no longer
  makes the A/B locator store overwrite its counts, and a torn last line in
  the cost or self-healing log no longer swallows the next record.

- **SQLite-backed stores.** Two dispatchers can no longer enqueue the same
  work-item reference; `WorkQueue.fail` on an unknown id raises instead of
  reporting a requeue; the work queue, checkpoint store and agent memory
  close their connections; a run-history or audit-log database error is an
  `AutoControlException` (`HistoryStoreError`, `AuditLogError`) instead of a
  `sqlite3.Error` that ended the hotkey listener thread; and two processes
  writing one audit log keep its hash chain valid.

- **Credentials no longer follow a redirect to another host.** The HTTP
  client drops `Authorization` and cookies when a redirect changes host. The
  Jira, Linear and GitHub failure-hook backends and the Slack bot now obey
  the egress policy and refuse redirects, and a non-object JSON reply is a
  failed call instead of an exception that stopped the Slack poll loop.

- **Remote-desktop file transfers cannot leave partial files or destroy the
  original.** Both receivers write to a `.part` file and rename it into place
  only when exactly the announced number of bytes arrived; excess or missing
  data fails the transfer. The WebRTC inbox refuses Windows device names
  (`nul`, `COM1.txt`) and names ending in a dot or space, and a malformed
  envelope or destination fails the transfer instead of killing the
  connection's receive thread.
- **One misbehaving admin host no longer fails every host's poll**, and an
  address book whose `hosts` is not a list loads empty instead of raising.

- **A failing data step no longer aborts the script.** SQLite, CSV, regex,
  PDF and malformed-HTTP errors from `AC_sql_to_var`, `AC_assert_db`,
  `AC_for_each_row`, `AC_transform_var`, `AC_pdf_to_var` and the HTTP
  commands are recorded like any other failed action; `AC_otp_to_var`
  refuses `step <= 0` instead of dividing by zero.
- **HTTP redirects obey the egress policy.** Only the first URL was checked,
  so an allowed host could redirect a request anywhere, including `ftp://`.

- **Reports.** A recorded control character (an ANSI colour code, a stray
  `\x01`) no longer breaks the XML report or makes a JUnit file unreadable;
  such characters appear as U+FFFD. A report that cannot be written raises
  `AutoControlHTMLException`, `AutoControlGenerateJsonReportException` or
  `XMLException` instead of being logged and skipped, and reports are written
  atomically. Exception text is no longer wrapped in an extra pair of quotes.

- **Vault passphrases and secret values no longer reach logs or results.**
  The arguments of `AC_secret_*` commands are shown as `***` in the
  executor's log lines and in the keys of the record it returns (a secret
  command's key changes accordingly), and the socket server no longer logs
  the command text.
- **Changing the vault passphrase cannot lose secrets.** The vault is
  rewritten once, atomically, instead of being deleted and refilled.
  `SecretStoreError` is now also an `AutoControlException`.
- **Config-bundle imports keep every backup.** Two imports in the same
  second no longer overwrite the first `.bak` file.

- **`JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS` covers every way a file runs.**
  Only `execute_files` checked it: the CLI's `run`, the scheduler, triggers,
  webhooks, hotkeys, the MCP `execute_action_file` tool and the GUI ran
  unsigned files with enforcement on, and `execute_files` itself verified one
  read of the file and parsed another. All of them now load through the new
  `read_executable_action_json`, which verifies and parses the same bytes.
- **Signing and encryption keys.** Key files are created 0600 in one step and
  never overwritten by a concurrent process; a key file shorter than 32
  bytes, which an interrupted first run could leave empty, is refused instead
  of being used as an empty HMAC key. An empty explicit key or passphrase is
  refused.

- **Cron expressions follow standard cron, and a job with no next run stops.**
  With both day fields restricted a day now matches if *either* does
  (`0 0 1 * 1` is the 1st and every Monday, as in Vixie cron and croniter;
  it was the Mondays that fall on the 1st), `7` is accepted as Sunday, and
  `5/15` is `5,20,35,50` rather than `5`. `0 0 29 2 *` failed to find its next
  run whenever the next leap day was over a year away, and the scheduler then
  fired that job on every tick; the search covers eight years, and a job whose
  next run cannot be computed is removed and logged. Migration: an expression
  with both day fields restricted fires on more days than before — write one
  of them as `*` to keep the old intersection.
- **`AllOf` triggers no longer lose a cron minute, file change or sequence
  step to a false sibling.** The edge child was checked first and spent its
  event before a later condition failed; edges are now checked last.
- **E-mail triggers leave mail unread with `mark_seen=False`.** The fetch
  itself set `\Seen`; it uses `BODY.PEEK[]`.
- **A webhook whose script fails with any exception answers 500.** Types
  outside four caught ones were recorded as a success and dropped the
  connection without a reply.

- **USB passthrough claims stalled, leaked and outlived their viewer.** After
  the first 16 transfers every request failed with "credit exhausted" — the
  host granted the viewer more credit with each reply but never counted it
  itself — and each failure counted as abuse. Claims were never released when
  the viewer's channel closed or the host stopped, leaving the device open and
  its kernel drivers detached (a claimed keyboard or mouse stayed gone). After
  65,534 claims the id counter wrapped onto a live claim and orphaned its
  handle.

- **Multi-viewer WebRTC host: sessions that outlived their viewer.** A
  viewer waiting on the Accept/Reject dialog was torn down by the 5-second
  auth deadline, so the user approved a dead session. A session whose peer
  connection failed or closed stayed registered — `session_count` only grew
  and screen capture never stopped once the last viewer left. An offer that
  failed (consent refused, timeout) left a session the caller never learned
  the id of, and the host-service daemon left one behind on every answer that
  did not arrive within 300 s. All four now end the session.

- **Flow control: seven ways a script did something other than it said.**
  A failed assertion inside an `AC_parallel` branch, or in an `AC_retry` that
  ran out of attempts, was wrapped into an ordinary error and swallowed under
  `raise_on_error=False`; it now propagates like any other assertion.
  `AC_break` / `AC_continue` with no enclosing loop escaped `execute_action`
  entirely and skipped the rest of the script; they are now a recorded failure
  ("outside a loop"). A macro that calls itself recursed until Python's limit
  (or, with two self-calls, ran exponentially long); calls now fail past
  `MAX_MACRO_DEPTH` (50) and the failure is recorded at the top level. An
  empty macro, `AC_assert_duration` body or `AC_parallel` branch is a no-op,
  as empty bodies are everywhere else, instead of an error. `AC_wait_image` /
  `AC_wait_pixel` with `timeout` 0 now look once instead of never.

- **A USB watcher stopped while it was still taking its first inventory
  forgot that inventory.** The poller discarded its priming enumeration
  whenever `stop()` had been called, not only when a newer `start()` had
  replaced it, so a following `poll_once()` reported every connected device
  as newly added — or not, depending on which side of the enumeration the
  stop landed. It now discards it only when superseded.

- **On Windows the key name `down` pressed F17 instead of the Down arrow.**
  The Windows `keyboard_keys_table` was built from every constant in
  `win32_vk.py`, including the `MOUSEEVENTF_*` and `KEYEVENTF_*` flags, and
  `down` was `MOUSEEVENTF_XDOWN` (0x80), which is `VK_F17`. It is now `VK_DOWN`,
  as on Linux and macOS. The 18 other names that were flags rather than keys
  are gone from the table, so a script using one fails with "unknown key"
  instead of pressing whatever key shares its value (`middledown` pressed
  space, `move` and `xbutton1` sent the left-button code): `absolute`,
  `eventf_extendedkey`, `eventf_keyup`, `eventf_scancode`, `eventf_unicode`,
  `hwheel`, `leftdown`, `leftup`, `middledown`, `middleup`, `move`,
  `rightdown`, `rightup`, `xbutton1`, `xbutton2`, `vktovsc`, `wheel`, `xup`.
  Migration: click mouse buttons through the mouse API (`mouse_x1`,
  `mouse_x2`, `mouse_left`…); `vk_xbutton1` / `vk_xbutton2` remain for the
  side-button virtual keys.

- **Recording on Windows lost touchpad scrolling up and multiplied it down.**
  A precision touchpad reports the wheel in fractions of a notch (typically
  ±30 of 120), and the recorder floored each event separately: `30 // 120` is
  0 and `-30 // 120` is -1. Scrolling up vanished from the recording and
  scrolling down replayed about four times too far. The hook now carries the
  remainder until it makes a whole notch, and drops it when the direction
  reverses.

- **The scheduler could start a job again while it was still running.** A job
  is rescheduled only after it finishes, so until then it still looks due. A
  single loop cannot overlap itself, but after a `stop()` whose join timed out
  inside a long job, the new run's loop saw the job as due and started a second
  copy. `Scheduler` now tracks the jobs it is executing and skips them.

- **A remote desktop viewer from a stopped host could attach to the restarted
  one.** `RemoteDesktopHost`, `RemoteDesktopRelay` and `RemoteDesktopViewer`
  had the same shared-event restart as the services below. On the host it
  mattered most: the accept loop performs the auth handshake (up to 60 s)
  before re-checking the stop flag, so a handshake begun before `stop()` and
  finished after the next `start()` passed that check and attached a viewer
  authenticated against the old run to the new one. On the viewer, a receiver
  outliving `disconnect()` marked the *next* connection as disconnected and
  reported its own closing socket through that connection's `on_error`. Each
  run now has its own event, and a receiver only touches its own connection.

- **Restarting a background service could leave the old loop running beside
  the new one.** Sixteen services — the scheduler, trigger engine, e-mail
  triggers, hotkey daemon, screen observer, popup watchdog, clipboard history,
  resource profiler, accessibility recorder, MCP plugin watcher, folder sync,
  ACME renewal, USB loopback, USB/IP server, the macOS recorder tap and the
  Slack bot — stopped by setting an event and joining with a timeout, and
  started by calling `clear()` on that same event. When the join timed out
  because the loop was inside a long iteration (a scheduled job, a hotkey
  action), the next `start()` cleared the event the old loop was waiting for
  and it resumed, untracked: every scheduled job ran twice, every hotkey fired
  twice. Each run now gets its own event, passed to its loop, so a stopped run
  stays stopped.

- **Restarting the USB hotplug watcher could leave a second poller running.**
  `UsbHotplugWatcher.stop()` waited only 2 s for the poller, but one
  enumeration (PowerShell `Get-PnpDevice`, `lsusb`, `system_profiler`) may
  take up to its 10 s subprocess timeout, so `stop()` could return — and
  `AC_usb_watch_stop` report `running: false` — while the thread was still
  running. A following `start()` then called `clear()` on the same stop
  event, and the old poller carried on beside the new one, untracked, for the
  life of the process. Each run now gets its own event, a poller stopped
  mid-enumeration no longer overwrites a newer run's snapshot, and `stop()`
  waits for up to the subprocess timeout plus one second, logging a warning
  if the poller is still running after that.
  `usb_devices.SUBPROCESS_TIMEOUT_S` is now public (it was `_SUBPROCESS_TIMEOUT_S`).

- **A failing `hotkey()` or `type_keyboard()` left keys held down.** Both
  press and then release with nothing protecting the gap, and their
  `except (OSError, RuntimeError, AttributeError, TypeError, ValueError)` does
  not cover `AutoControlKeyboardException` — the error `press_keyboard_key` /
  `release_keyboard_key` actually raise for an unknown key name, an unsupported
  platform or a backend failure. So `hotkey(["ctrl", "shift", "esc"])` failing
  on `esc` left `Ctrl` and `Shift` down on the real keyboard, changing the
  meaning of every later click and keystroke. The release now runs from
  `finally`: only keys that were actually pressed and not yet released are
  released, in reverse order, and a release that fails during that cleanup is
  logged rather than raised, so the caller still sees the original error.

- **The Windows recorder dropped mouse side buttons.** Playback has always
  accepted `mouse_x1` / `mouse_x2`, but the low-level hook keyed its button
  table by message id, and `WM_XBUTTONDOWN` / `WM_XBUTTONUP` are one id for
  both buttons (which one is in the high word of `mouseData`). Side clicks were
  therefore never recorded, and a macro replayed without them with no warning.
  `stop_record_timeline()` now yields `mouse_down` / `mouse_up` events with
  `button` `"x1"` / `"x2"`, and `replay_timeline()` maps them to `mouse_x1` /
  `mouse_x2`. An unrecognised side-button value is dropped rather than guessed,
  because the replay side falls back to the left button for a name it does not
  know. The legacy down-events-only queue (`stop_record()`) still omits them:
  there is no `AC_mouse_x1` command to put in it.

- **Changing a hotkey's combo on X11 left the old key grabbed for the life of
  the daemon.** `LinuxHotkeyBackend._sync_one` dropped the previous
  registration from its own table without calling `ungrab_key`, so the *old*
  combo stayed grabbed on the X server: it was swallowed from every
  application, fired nothing, and `_ungrab_all` could not release it at
  shutdown because it no longer knew about it. Rebinding `ctrl+alt+k` to
  something else made `ctrl+alt+k` dead system-wide until the process exited.
  The Windows backend has always unregistered at the same point; the X11 one
  now does too. Unaffected on Windows and macOS.

- **A window closing mid-call let a COM error escape every Windows
  accessibility read.** `comtypes` reports a provider failure as `COMError`,
  which derives straight from `Exception` — the reason
  `windows_query._uia_errors()` exists — but only the two tree-walking guards
  in `backends/windows_backend.py` used that tuple. The other 37, covering
  every control pattern (`get_value`, `invoke`, `toggle`, `read_table`, the
  text and grid reads, …), named `(OSError, AttributeError, …)` and therefore
  contained none of them. An application that stopped responding, or a window
  that closed between the search that found an element and the call that read
  it, raised `COMError` out of the `ac_*` tool or `AC_*` command instead of
  answering `None` / `False` / `[]`, and past the executor's
  `AutoControlException` boundary. All 37 now use the same tuple. This only
  widens what is caught: no call that used to succeed behaves differently.

- **The WebRTC viewer ended every clean disconnect with an unhandled task
  exception.** `WebRTCDesktopViewer._consume_video` caught
  `(OSError, RuntimeError)`, but aiortc signals the end of a track by raising
  `MediaStreamError`, which derives straight from `Exception` and so matched
  neither. Nothing awaits that task, so the normal end of a session — the host
  stopping its screen share, or the connection closing — reached the console as
  asyncio's "Task exception was never retrieved" traceback instead of the
  "video stream ended" line the host's own drain loop already logged. The
  stream is unaffected either way; only the logging changes.

- **A `null` in a remote-desktop entry's `tags` became a tag named `"None"`.**
  `AddressBook.set_tags()` cleaned its input with `str(t).strip()`, and
  `str(None)` is the non-empty string `"None"`, so a JSON `null` in the array —
  what a client sends for an omitted tag — was stored as a tag and then listed
  by `all_tags()` alongside the real ones. Nulls are now dropped. Tags that
  were already stored this way stay until the entry's tags are set again.

## [0.0.222] - 2026-08-23

### Changed

- **`mouse_scroll()` rejects a scroll direction the platform has no axis for.**
  A name outside `special_mouse_keys_table` used to be passed down to the
  backend unchanged, which meant `int('scroll_upp')` on Wayland and uinput and
  an Xlib failure on X11 — deep in the backend, with the offending name nowhere
  in the message. It now raises `AutoControlCantFindKeyException` naming the
  direction, the same answer the button table has always given for an unknown
  button name. Windows and macOS are unaffected: they have a single wheel axis
  and never read the direction.

- `je_auto_control.stop_record()` returns an empty list where it used to
  return `None`. It has always been annotated `-> list`, but the failure path
  fell off the end of the function, so a caller that did not write
  `stop_record() or []` iterated over `None` and raised in its own code
  instead. `stop_record_timeline()` already returned `[]` on the same
  failure; the two now agree.

- `je_auto_control.mouse_scroll()` reports its return type as
  `Tuple[int, Union[int, str]]`. The value has not changed — X11 and Wayland
  still hand back the backend axis code the direction name resolved to, and
  every other platform the name itself — the signature just no longer claims
  it is always a `str`.

- The Windows screen backend's `size()` returns a `tuple`, not a `list`.
  The macOS, X11 and Wayland backends all returned tuples already, and the
  public `screen_size()` has always been annotated `Tuple[int, int]`; every
  caller unpacks the two values, so nothing that used it needs changing.

### Fixed

- **Typing text through the key-event route raised `AttributeError` on the
  three platforms that cannot do it.** `type_unicode_keys()` (and
  `AC_type_unicode_keys` / `ac_type_unicode_keys`) called the backend's
  `type_unicode_unit` outright, and only Windows has one, so macOS, X11 and
  Wayland raised an exception from outside the `AutoControlException` family
  that the executor, the background poll loops and the request handlers each
  catch in one `except` — it escaped every containment boundary in the
  project. It now raises `AutoControlKeyboardException` pointing at
  `type_unicode_text()`, which picks a route that works on any platform.

- **A backend that could not report the cursor aborted the script instead of
  raising what the API promises.** `press_mouse` / `release_mouse` /
  `click_mouse` with an omitted `x` or `y` unpacked `get_mouse_position()`
  without checking it for `None`, so a backend that answers "I don't know"
  raised `TypeError` from the unpacking — outside the
  `AutoControlMouseException` family every containment boundary catches. It
  now raises `AutoControlMouseException`. `mouse_scroll` reached the same
  unpacking through `_scroll_to` and now skips the pre-move instead, which is
  the graceful degradation its own comment already documented for backends
  that cannot report the cursor.

- **`je_auto_control.windows.message.window_message` could not be imported
  at all.** It did `from ...windows_window_manage import FindWindowW`, and
  that module has no such name — `FindWindowW` is a method on its private
  `user32` handle — so importing `window_message` raised `ImportError` on
  every Windows machine. It now calls the module's public
  `get_one_window_hwnd`, which is also the one that declares HWND-width
  argtypes rather than letting ctypes truncate a 64-bit handle to `c_int`.

- **Importing the Win32 input backend no longer writes into
  `ctypes.wintypes`.** `win32_ctype_input` set `wintypes.ULONG_PTR =
  wintypes.WPARAM` on the standard library's own module. Nothing in this
  package ever read it back, so the only effect the assignment could have was
  on some other library in the same process asking `ctypes.wintypes` whether
  it has `ULONG_PTR`.

- **Stopping an X11 recording that was never started raised instead of
  returning nothing.** The X11 listener's `stop_record()` handed back the
  `None` its queue attribute was constructed with, and the recorder one frame
  up reads `.queue` off that result, so `stop_record()` without a preceding
  `record()` produced an `AttributeError` that the wrapper caught and logged
  as a failure. It now returns an empty queue, so the public `stop_record()`
  returns the empty list it documents.

- **`check_key_is_press()` passed `None` to the backend for an unknown key
  name.** A name the virtual-key table has no entry for became `None` and was
  handed to the platform backend anyway: a `TypeError` on Windows and a silent
  `False` on X11 — that is, "no, it is not pressed" for a key that does not
  exist. It now logs the lookup failure and returns `None`, which is the
  documented "could not answer" value.

## [0.0.221] - 2026-08-20

### Added

- **Windows on arm64 installs.** `opencv-python`, `cryptography` and
  `je_open_cv` now carry the environment marker
  `sys_platform != 'win32' or platform_machine != 'ARM64'`, because none of
  the three publishes a `win_arm64` wheel and `pip install je_auto_control`
  therefore failed on that platform before any of this code ran. Every other
  platform resolves exactly the same dependency set as before. On Windows
  arm64, the features that need those wheels — `find_image*`, the OpenCV
  `screenshot()`, the secret vault, action-file encryption, ACME/TLS and
  encrypted recording — raise a `RuntimeError` or `ImportError` naming the
  missing wheel rather than a bare `ModuleNotFoundError`. Python 3.11 is the
  floor there, since CPython publishes no official Windows arm64 build for
  3.10.

## [0.0.220] - 2026-08-20

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

- **MCP sessions over HTTP.** `initialize` now mints an `Mcp-Session-Id` and
  returns it as a response header. A client that echoes it keeps one
  dispatcher scope — the capabilities it advertised, and the slots its
  in-flight calls occupy — across every connection it opens, instead of one
  scope per TCP connection. `GET /mcp` with `Accept: text/event-stream` and a
  valid session id opens the standing server-to-client SSE stream (one per
  session; a second gets 409), `DELETE /mcp` with the id terminates the
  session, and a server request is answered by `POST`ing an ordinary JSON-RPC
  response on any connection. Sessions are swept after ten minutes untouched
  and capped at 128. `je_auto_control.utils.mcp_server.http_sessions` holds
  the registry.

- **`JE_AUTOCONTROL_MCP_CONFIRM_DESTRUCTIVE=1` now works over HTTP** — for a
  client that echoes `Mcp-Session-Id` and holds the `GET` stream open. It
  previously fired only on stdio: the prompt needs a server-to-client channel
  bound to the scope that received `initialize`, and a connection-keyed scope
  never survived to the `tools/call`. A client that does neither still cannot
  be prompted and its destructive calls still proceed, exactly as for a stdio
  client that never advertised `elicitation`; that fallback is documented and
  is not a substitute for the bearer token, the `127.0.0.1` bind or
  `JE_AUTOCONTROL_MCP_READONLY`.

### Changed

- The MCP HTTP transport answers `GET /mcp` differently. It used to return
  `405` with `{"error": "GET stream not supported"}` for every request; it now
  serves the session's SSE stream when the request carries
  `Accept: text/event-stream` and a valid `Mcp-Session-Id`, and still returns
  `405` when the `Accept` header does not ask for a stream. A request — of any
  method — carrying an `Mcp-Session-Id` the server does not know is refused
  with `404` rather than served under a fresh scope, which is the signal to
  re-run `initialize`. `DELETE /mcp` without a session header is still
  accepted as a no-op, so clients that never adopt sessions are unaffected.

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

### Fixed

- The MCP HTTP transport no longer tries to drain a request body it has
  already read. Any `4xx` decided *after* the body was parsed — the new
  unknown-session `404` and duplicate-stream `409`, and the pre-existing
  "body must be UTF-8" `400` — called `_drain_body()`, which then blocked
  reading bytes that were gone until the 30-second socket timeout, pinning
  that worker and logging a `ConnectionAbortedError` traceback when the peer
  closed first. The drain is now skipped once the body is consumed, and a
  peer that has already vanished ends it quietly instead of raising.

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

## [0.0.219] - 2026-08-19

### Added

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

- `JE_AUTOCONTROL_WAYLAND_POINTER_ACCEL` — how an operator declares what the
  library cannot read back. `flat` says pointer acceleration is off for the
  ydotoold device, so an absolute move through the ydotool fallback is exact
  and needs no warning; `strict` refuses that move instead of letting a click
  land somewhere else; unset (or any unrecognised value, which says so and
  falls back) keeps the existing warn-once-and-move behaviour. The libei path
  is absolute at the protocol level and is not affected either way.

### Changed

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

### Deprecated

- `send_key_event_to_window` and `send_mouse_event_to_window` — use
  `post_key_to_window` / `post_click_to_window`. Both now emit a
  `DeprecationWarning` and delegate to the working implementation; see Changed
  for the behaviour that changes.

### Removed

- `je_auto_control.linux_wayland._detect.WAYLAND_GDBUS` is gone, along with the
  `gdbus` probe it named: the desktop-portal capture tier no longer shells out
  to any binary. `_detect` is a private module and nothing else referenced the
  constant.

### Fixed

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

## [0.0.218] - 2026-08-16

### Added

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

## [0.0.217] - 2026-07-23

No compatibility changes.

## [0.0.216] - 2026-07-23

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
