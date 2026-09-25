# docs/updates: update log index

`Progress.md` holds only work that is **not done yet**. Everything that *was* done (what changed, measured numbers, decisions, snapshots) is recorded here: **one batch file per month**, one entry per piece of work, each entry with a fixed-format ID and tags, and one row per entry in the index below.

> No TODOs here. If an entry mentions something still open, it only points to it (e.g. "open item: `Progress.md` #3"); the item itself lives in `Progress.md`.

## How to query

Run from the repository root:

| To find | Command |
|---|---|
| every entry, one line each | `rg -n "^## U-2" docs/updates` |
| entries of one type | `rg -n "^## U-2.*#done" docs/updates` |
| entries with a topic tag | `rg -n "^## U-2.*#<tag>" docs/updates` |
| one day or one month | `rg -n "^## U-202609" docs/updates` |
| the full text of one entry | `rg -n -A 60 "^## U-20260922-01" docs/updates` |
| any keyword | `rg -n "keyword" docs/updates` |

Without `rg`: `git grep -n "^## U-2" -- docs/updates`, or in PowerShell `Select-String -Path docs/updates/*.md -Pattern '^## U-2'`.

## Entry format

```markdown
## U-YYYYMMDD-NN · YYYY-MM-DD · one-line title · #type #topic

- **What**: ...
- **Result / numbers**: ...
- **Files**: `path` ...
- **Evidence**: commit, file:line, link ...
- **Open items**: none / see `Progress.md` ...
```

- **ID**: `U-` + date + two-digit sequence for that day. IDs are never renumbered or reused, so code comments and other documents can cite them.
- **Type tag** (exactly one): `#done` finished `Progress.md` item, `#snapshot` measurement or inventory, `#decision`, `#incident`, `#migration`, `#docs`, `#release`.
- Topic tags are free-form (`#mcp`, `#wayland`, ...).
- Keep conclusions, numbers, files and evidence; drop the reasoning trail and dead ends.

## Batch rules

1. One file per month: `docs/updates/YYYY-MM.md`. Append new entries at the end.
2. Over about 800 lines, continue in `YYYY-MM-b.md` (then `-c`) and list it in the batch table below.
3. **Claim the ID under a lock.** Several sessions may write this log at the same time (for example parallel autonomous runs), and without a lock two of them pick the same number:
   1. `mkdir docs/updates/.id-lock`. Creating a directory is atomic, so only one writer succeeds. If it already exists, someone else is claiming: wait a few seconds and retry. A lock older than 10 minutes is stale and may be removed.
   2. Find the day's last number with `rg -n "^## U-YYYYMMDD" docs/updates` and write the heading line and the index row.
   3. `rmdir docs/updates/.id-lock`, then fill in the body. Git never tracks the empty lock directory.
   4. Before committing, `rg -c "^## U-<your ID>" docs/updates` must report one match in total. If not, renumber your entry under the lock and fix its index row. Whoever merges a branch renumbers entries that reuse an ID.
4. **One line per index row**: title only (about 60 characters), no summary.
5. Never rewrite a recorded entry. Correct it with a new `#decision` or `#incident` entry and add "→ corrected in U-..." to the old one.

## When a `Progress.md` item is done

In the same commit: delete the item from `Progress.md`, add a `#done` entry here that names it, and add its index row.

---

## Index (newest first)

| ID | Date | Title | Tags | Batch |
|---|---|---|---|---|
| U-20260925-42 | 2026-09-25 | Every numeric line edit validates in the C locale through one helper: under French or German the Image Detect threshold could not be changed, and a grouped integer passed the validator but not int() | #bugfix #gui #i18n | [2026-09-d](2026-09-d.md) |
| U-20260925-41 | 2026-09-25 | Script Builder: shown defaults match the executor (an edit no longer loosened an exact image match), required fields are required, positional arguments and wrapped files survive load and save, decimals can be typed under comma locales, odd RGB values load, and a new loop takes children | #bugfix #gui #script-builder | [2026-09-d](2026-09-d.md) |
| U-20260925-39 | 2026-09-25 | WebRTC panels and Quick Connect sessions: remote annotations are checked and bounded, the tray keeps the app alive only while hosting, a host stopped under the approval dialog or the stats thread is not an error, imports survive files of the wrong shape, Stop cancels a pending reconnect, a new window keeps the pen, empty recordings are not called saved, and Quick Connect treats ws:// sessions, errors and approval timeouts properly | #bugfix #remote-desktop #gui | [2026-09-d](2026-09-d.md) |
| U-20260925-38 | 2026-09-25 | Codacy's gate on PR #489 had seven findings: subprocess rules on building a CompletedProcess or TimeoutExpired, a taskkill call reported one line below its marker, exec in a codegen test, a stdlib xml import that the test needs, and an unassigned QApplication | #ci #codacy | [2026-09-d](2026-09-d.md) |
| U-20260925-37 | 2026-09-25 | Remote desktop panels: Quick Connect verifies wss:// and forwards input, closing a session window no longer aborts the process, connect slots report every error, audio follows its box with the section collapsed, the share text quotes the running host, signaling and the USB browser go through http_client | #bugfix #remote-desktop #gui #security | [2026-09-d](2026-09-d.md) |
| U-20260925-36 | 2026-09-25 | A sweep of less-visited utils subpackages: three locators answer in screen coordinates, the voice router is thread-safe, failure signatures ignore unit-glued numbers, delta counts match their summary, no home directory is survivable, infinite samples and clipped checkboxes, dominant contrast colours, opaque URL schemes | #bugfix #vision #audit | [2026-09-d](2026-09-d.md) |
| U-20260925-35 | 2026-09-25 | SonarCloud's reliability gate failed on the OpenAI backend's first-choice read; it now takes the choice without indexing | #ci #agent | [2026-09-d](2026-09-d.md) |
| U-20260925-34 | 2026-09-25 | Window and OS helpers at their edges: file dialogs need the exact title and the front before typing, watchdog keys go to the popup, psutil and regex errors are framework errors, empty needles are refused, file drops use absolute paths, the Window Manager acts on the selected window; input paths Jeffrey_RPA runs are recorded, not changed | #bugfix #windows #gui | [2026-09-d](2026-09-d.md) |
| U-20260925-33 | 2026-09-25 | Integration helpers at their edges: secrets nested in arguments are masked, credentials stay behind on redirects, assert_http and config sync go through http_client, Office / S3 / SQLite errors stay in the framework family, the IMAP trigger fires once per message and names any mailbox, cassettes keep no credentials | #bugfix #security #integration | [2026-09-d](2026-09-d.md) |
| U-20260925-32 | 2026-09-25 | Two new audit tests failed CI: the window probe needs qt_material, which the headless jobs lack, and 3.14 on Linux and macOS parses JSON nested 50,000 deep | #testing #ci | [2026-09-d](2026-09-d.md) |
| U-20260925-31 | 2026-09-25 | The LLM / VLM / agent layer at its edges: a turn cut short never runs its tool calls, tool schemas carry real types, coordinates survive strings and scaling, VLM replies are read in the image the model saw and request failures are errors, OpenAI refusals are not answers, reused backends start fresh | #bugfix #agent #vlm | [2026-09-c](2026-09-c.md) |
| U-20260925-30 | 2026-09-25 | Accessibility and OCR at their edges: a closed window's COMError is contained, FindText's NULL range is not found, macOS bounds are real, elements with no rectangle are not clicked, audits read Windows roles, the recorder survives framework errors, the Linux search has a node budget | #bugfix #accessibility #ocr | [2026-09-c](2026-09-c.md) |
| U-20260925-29 | 2026-09-25 | The GUI exit probes time the exit itself, not interpreter start-up, so a loaded machine no longer fails them | #testing #gui | [2026-09-c](2026-09-c.md) |
| U-20260925-28 | 2026-09-25 | Shell, clipboard, adb and USB/IP helpers at their edges: AC_shell_to_var refuses cmd syntax for batch files, timeouts end the whole process tree, launch failures fail the action, secrets stay out of logs, an empty Linux clipboard is empty, USB/IP device lists, speeds, idle devices and isochronous URBs | #bugfix #security #usbip | [2026-09-c](2026-09-c.md) |
| U-20260925-27 | 2026-09-25 | Code generation, the command-line tools and report writers at their edges: MCP --read-only reaches the server, MCP stdio and CLI output are UTF-8, generated tests fail with their actions, ${var} goes through the executor, action shapes are checked, SARIF / SOP / Allure output | #bugfix #codegen #mcp #cli | [2026-09-c](2026-09-c.md) |
| U-20260925-26 | 2026-09-25 | The package imports cleanly when warnings are errors, and SARIF file URIs no longer use PurePath.as_uri(), deprecated in Python 3.14 | #bugfix #compat | [2026-09-c](2026-09-c.md) |
| U-20260925-25 | 2026-09-25 | The September update log is split at 800 lines into 2026-09.md, -b and -c, as the batch rules ask | #docs | [2026-09-c](2026-09-c.md) |
| U-20260925-24 | 2026-09-25 | The MCP server speaks 2025-11-25: it negotiates the revision, describes itself to its clients, and reports input validation errors as tool execution errors the model can correct | #feature #mcp | [2026-09-c](2026-09-c.md) |
| U-20260925-23 | 2026-09-25 | GUI tabs at their edges: slots show framework errors, USB sharing and the Live HUD are released when their tab goes, hidden tabs are owned, a worker's unexpected exception reaches on_fail, the Script Builder keeps a choice it does not list, the window's language listener and each USB prompt's dialog go with their owners | #bugfix #gui #security | [2026-09-c](2026-09-c.md) |
| U-20260925-22 | 2026-09-25 | Servers and report helpers at their edges: replies that cannot be encoded or serialised, bodies nested too deeply, a history limit SQLite cannot bind, conflicting Content-Length, 401 challenges, 405 with Allow, escaped access logs, an empty host filter, config-sync ties that converge, one +Inf bucket, an FPS-only profiler that knows it runs | #bugfix #rest #mcp #security | [2026-09-c](2026-09-c.md) |
| U-20260925-21 | 2026-09-25 | Runtime flow at its edges: runs with a failed action are recorded as errors, macro parameters are restored after a call, */15 keeps its pace through the repeated DST hour, watchdog rules are contained, re-enabled jobs wait, interval jobs do not drift, replaced triggers, hotkey start/stop, retry backoff, plugin names | #bugfix #scheduler #flow | [2026-09-c](2026-09-c.md) |
| U-20260925-20 | 2026-09-25 | A viewer that disconnects while its upload's FILE_BEGIN is opening the part file no longer leaves the .part file and its handle behind | #bugfix #remote-desktop | [2026-09-c](2026-09-c.md) |
| U-20260925-19 | 2026-09-25 | The action JSON Schema lists block commands and types parameters from their resolved annotations; the linter checks block commands' required arguments | #bugfix #tooling | [2026-09-c](2026-09-c.md) |
| U-20260925-18 | 2026-09-25 | Scripting, recording and locator helpers at their edges: dotted trigger variables resolve, repair verdicts in every form, torn heal-log lines, A/B stats across stores, actions before the first frame, CJK recall, BOM variable files, a new trace per reset | #bugfix #scripting | [2026-09-c](2026-09-c.md) |
| U-20260925-17 | 2026-09-25 | Remote-desktop workers run on daemon threads: exiting during a signaling long-poll, or closing the viewer mid-transfer, no longer aborts the process | #bugfix #gui #remote-desktop | [2026-09-c](2026-09-c.md) |
| U-20260925-16 | 2026-09-25 | Tests carry no unused imports: 20 removed across 16 test modules, and one lambda assignment made a def | #test #cleanup | [2026-09-c](2026-09-c.md) |
| U-20260925-15 | 2026-09-25 | Test-infrastructure and statistics helpers at their edges: re-merged shard reports, bucket edges at Unix time, regex assert_text ignore_case, the screen-stable clock, the documented cost summary and current Claude prices, huge ints in validate_rows, the t quantile for tiny alpha | #bugfix #testing #data | [2026-09-c](2026-09-c.md) |
| U-20260925-14 | 2026-09-25 | The MCP server negotiates only versions it speaks, declares only server capabilities, refuses an unsupported MCP-Protocol-Version header with 400, and asks for sampling only from a client that declared it | #bugfix #mcp | [2026-09-c](2026-09-c.md) |
| U-20260925-13 | 2026-09-25 | Screenshots are fitted with the vision docs' exact resize rule, and AC_run_agent's Anthropic backend fits its screenshots and maps tool-call x / y back | #bugfix #agent | [2026-09-c](2026-09-c.md) |
| U-20260925-12 | 2026-09-25 | Supply-chain formats follow their specs: OpenVEX affected needs an action statement, SLSA provenance omits empty metadata and reports nameless subjects, PEP 440 orders post/dev releases and implicit numbers, redaction boxes merge transitively | #bugfix #security | [2026-09-c](2026-09-c.md) |
| U-20260925-11 | 2026-09-25 | Security helpers hold at the edges: IDNA hosts in the egress policy, OSV ranges with several pairs, licence spellings and every licence entry, whole-placeholder secrets only, locked in-memory gates and broker, PEP 639 licences, print-format IBANs, escaped quotes, SARIF without severity, a colleague called Dan | #bugfix #security | [2026-09-c](2026-09-c.md) |
| U-20260925-10 | 2026-09-25 | observation_delta inherits element matching's IoU > 0 rule; its moved-element test now uses boxes that overlap | #test #vision | [2026-09-c](2026-09-c.md) |
| U-20260925-09 | 2026-09-25 | Computer use on the beta tool fits screenshots into the model's image tier and maps coordinates back, so clicks land where the model meant on screens over the limit | #bugfix #agent | [2026-09-c](2026-09-c.md) |
| U-20260925-08 | 2026-09-25 | Image helpers follow their references: pixelmatch's anti-aliasing test instead of a morphological open, L1 histograms with a symmetric intersection, SSIM on the images' dynamic range, the true median line height, no IoU-zero matches, arrays in the perceptual hashes | #bugfix #vision | [2026-09-c](2026-09-c.md) |
| U-20260925-07 | 2026-09-25 | Text helpers follow their references: diffs split at line feeds only, UTS #39 skeletons, a symmetric fuzzy fallback, sentences that hold a word, casefolding that stays normalised, Common-script x and division sign, bidi per paragraph | #bugfix #text | [2026-09-c](2026-09-c.md) |
| U-20260925-06 | 2026-09-25 | GUI workers run on daemon threads, so exiting during a long step no longer aborts the process: start_worker returns a WorkerHandle and there is no QThread left to destroy | #bugfix #gui #done | [2026-09-c](2026-09-c.md) |
| U-20260925-05 | 2026-09-25 | Computer toolset screenshots use the high-resolution image tier (2576 px, 4784 visual tokens) and zoom is implemented with a full-resolution crop | #feature #agent | [2026-09-c](2026-09-c.md) |
| U-20260925-04 | 2026-09-25 | Text-format helpers follow their references: ICU quoting, offset: 1 and infinite counts, French many, .mo charsets, single-quote escapes in .env, RFC 6901 $ref tokens, ; inside SQL literals, Infinity in parse_number | #bugfix #i18n #data | [2026-09-c](2026-09-c.md) |
| U-20260925-03 | 2026-09-25 | Stores keep data and secrets under contention and odd input: the secret vault locks across processes, JSON stores read a BOM and wait out a reader, cassettes redact set_cookie, truncated deflate is refused, x-gzip is gzip, WorkQueue and CheckpointStore raise their own errors | #bugfix #security #storage | [2026-09-c](2026-09-c.md) |
| U-20260925-02 | 2026-09-25 | Computer use and DAG runs can be stopped: stop_event on AgentLoop, run_computer_use and run_dag, Stop in the tabs' Actions menu, and closing the window asks running jobs to stop | #feature #gui #agent | [2026-09-c](2026-09-c.md) |
| U-20260925-01 | 2026-09-25 | Data-format helpers follow their specs: multipart keeps binary file bytes and backslashes in filenames, JSONPath != matches a missing member and filter strings may hold )], RRULE refuses parts it would ignore, LatencyDigest orders negative values | #bugfix #data | [2026-09-c](2026-09-c.md) |
| U-20260924-84 | 2026-09-24 | Protocol helpers follow their specs at the edges: JWT list alg and crit, SSE split CRLF, escaped quotes in Link and Cache-Control, newer traceparent versions, typed problem members, escaped unreserved URL characters, empty cookie values | #bugfix #http #security | [2026-09-c](2026-09-c.md) |
| U-20260924-83 | 2026-09-24 | Closing a tab or the window while its background job runs no longer aborts the process; the computer-use, DAG and LLM planner tabs share start_worker | #bugfix #gui | [2026-09-c](2026-09-c.md) |
| U-20260924-82 | 2026-09-24 | LAN browse dialogs stop their zeroconf browser however they close; the presence tab leaves the registry when destroyed | #bugfix #gui | [2026-09-c](2026-09-c.md) |
| U-20260924-81 | 2026-09-24 | Computer use speaks the GA computer_toolset_20260801 (Claude Opus 5.5 accepts nothing else); drags end where the model said, key repeat and click modifiers are honoured | #feature #bugfix #agent | [2026-09-c](2026-09-c.md) |
| U-20260924-80 | 2026-09-24 | Config-sync tombstones: the Progress item is closed (implemented in 37d0a4fc) | #done #config_sync | [2026-09-c](2026-09-c.md) |
| U-20260924-79 | 2026-09-24 | Remote action failures are reported: REST /execute takes raise_on_error, and the admin console and DAG remote nodes use it | #bugfix #done | [2026-09-c](2026-09-c.md) |
| U-20260924-78 | 2026-09-24 | GUI threads: workers that never ran now run, results land on the GUI thread, Quick Connect repaints off the receiver thread no more, stopped WebRTC signaling threads no longer abort the process | #bugfix #audit #gui | [2026-09-c](2026-09-c.md) |
| U-20260924-77 | 2026-09-24 | Replay traces survive Unicode line separators, persistence needs every frame, one modifier name is one key, unknown CI levels refused, off-frame change boxes score nothing, OTLP output is strict JSON, SOPs read every action-file shape | #bugfix #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-76 | 2026-09-24 | Utility audit: file drops free their block, zero-weight grounding, reading order in table cells, non-finite profiles, verify modes, collation accents and NFD, CF_HTML str offsets, role digits, HSV bounds | #bugfix #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-75 | 2026-09-24 | macOS media keys call the real PyObjC selector; the platform audit tests pass on Linux and macOS | #bugfix #test | [2026-09-b](2026-09-b.md) |
| U-20260924-74 | 2026-09-24 | Twenty-five errors that inherited only a builtin exception join the AutoControlException family | #bugfix #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-73 | 2026-09-24 | Audit tests import their subjects explicitly, which Codacy's import-injection rule accepts | #test #ci | [2026-09-b](2026-09-b.md) |
| U-20260924-72 | 2026-09-24 | X11, uinput and macOS backends: uinput types the right keys, send-to-window releases, unbound keys fail, wheel events recorded cleanly, media keys press and release, tap re-enabled | #bugfix #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-71 | 2026-09-24 | Wayland: libei devices survive a pause and are released once, wlr-randr sizes follow rotation and scale, a bad capture override is a screen error | #bugfix #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-70 | 2026-09-24 | WebRTC media: screen frames stamped at their real rate, host voice mixed down for mono players, audio device errors contained, a reusable viewer, mDNS and bridge cleanup | #bugfix #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-69 | 2026-09-24 | USB passthrough opens identical devices by serial, checks endpoint direction and releases interfaces; agent, self-heal, anchor, USB/IP and a11y fixes | #bugfix #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-68 | 2026-09-24 | MCP requests that always get a reply, a drag that releases, sampling over HTTP, waits that look once; USB credits and claims without races; assertions through callbacks; gamepad, clipboard and volume errors in the family | #bugfix #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-67 | 2026-09-24 | Remote desktop: RFC 6455 masking and control-frame rules, a handshake that survives a bad key, file transfers to no file, an honest encrypted recorder, restartable mic, host voice kept on | #bugfix #audit #security | [2026-09-b](2026-09-b.md) |
| U-20260924-66 | 2026-09-24 | Audit tests that only see their own file's leaks and pass Codacy | #test #ci | [2026-09-b](2026-09-b.md) |
| U-20260924-65 | 2026-09-24 | Make the poison-email regression test independent of the CPython patch release | #ci #test | [2026-09-b](2026-09-b.md) |
| U-20260924-64 | 2026-09-24 | Per-flow history for flow selection and sharding, depth-safe XY-cut, config env and lossless ints, null-aware uniqueness, CLDR unit lists, MIME-typed A2A modes, UIA Value / RangeValue ids | #bugfix #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-63 | 2026-09-24 | JSONPath quoting and RFC 9535 ordering, OCR fields read below their label, hardware encoders that really open, odd-sized H.264 frames | #bugfix #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-62 | 2026-09-24 | Text, config and registries: whole -or-later licences, strict REST booleans, .po entries without blank lines, CLDR plural operands, host-bound file URIs, coturn and XML injection | #bugfix #audit #security | [2026-09-b](2026-09-b.md) |
| U-20260924-61 | 2026-09-24 | Data utilities: JWT expiry and canonical segments, bounded similarity, framework DAG errors, strict time-series and schema arguments, safe flag serves | #bugfix #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-60 | 2026-09-24 | AC_idempotency_release: scripts and MCP clients can free a key whose work failed | #feature #done | [2026-09-b](2026-09-b.md) |
| U-20260924-59 | 2026-09-24 | Triggers, scheduler and data sources: serialised engine start/stop, poison-proof email polling, quoted mailboxes, answerable webhook verbs, numeric max_runs, contained .xlsx errors | #bugfix #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-58 | 2026-09-24 | Small utilities: implicit-SSL port, a profiler frozen at stop, strict Content-Length, WebRunner screenshots, notifications that report failure | #bugfix #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-57 | 2026-09-24 | Type-check the SBOM's optional packaging import in CI's bare install | #ci #typing | [2026-09-b](2026-09-b.md) |
| U-20260924-56 | 2026-09-24 | Emergency stop wakes a sleeping main thread on Linux and macOS too | #bugfix #ci | [2026-09-b](2026-09-b.md) |
| U-20260924-55 | 2026-09-24 | Image analysis and packaging: Machado CVD simulation, square-aware widget classes, repair that does not re-act, schema-valid registry manifests | #bugfix #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-54 | 2026-09-24 | Observation and state: an emergency stop that wakes a sleeping script, non-overlapping mark labels, strict placeholders, CloudEvents and coordinate spaces | #bugfix #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-53 | 2026-09-24 | File-dialog confirm and popup-watchdog keys resolve to the platform's key names | #bugfix #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-52 | 2026-09-24 | Input and form helpers: platform key names for computer use, linted flow bodies, working gamepad clicks and dpad, RTF code pages | #bugfix #audit #agent | [2026-09-b](2026-09-b.md) |
| U-20260924-51 | 2026-09-24 | Media and analysis: exact bucket edges, converged KS p-values, normalised histogram intersection, honest video motion and visual-diff percentages | #bugfix #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-50 | 2026-09-24 | Image matching: screen coordinates everywhere, masked rotated templates, flat templates refused on every path, per-blob peaks | #bugfix #audit #vision | [2026-09-b](2026-09-b.md) |
| U-20260924-49 | 2026-09-24 | System and device helpers: keep-awake that ends with the process, real content types, strict checksums and compliance, D-Bus and window-capture fixes | #bugfix #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-48 | 2026-09-24 | Agent and action helpers: assertions are never healed, releases follow healed presses, live actionability gates, innermost grounding | #bugfix #audit #agent | [2026-09-b](2026-09-b.md) |
| U-20260924-47 | 2026-09-24 | Stores set a file aside only when its content is damaged, not when a read fails | #bugfix #audit #remote-desktop | [2026-09-b](2026-09-b.md) |
| U-20260924-46 | 2026-09-24 | Config and plumbing: redacted failure tickets, contained plugin directories, Unicode search terms, sturdier chatops and trace spans | #bugfix #audit #security | [2026-09-b](2026-09-b.md) |
| U-20260924-45 | 2026-09-24 | Workflow and test tooling: merged shard reports keep errors, waits honour deadlines, strict hit policies and predicates, assert_poll is an assertion | #bugfix #audit #testing | [2026-09-b](2026-09-b.md) |
| U-20260924-44 | 2026-09-24 | Text processing: whole phone and Amex masking, linear PII and secret scans, invisible-character-proof confusables, TR39 script mixing, fuzzy .po entries skipped | #bugfix #audit #security | [2026-09-b](2026-09-b.md) |
| U-20260924-43 | 2026-09-24 | Locators and geometry: no fake sideways scroll, unique stable ids, points inside their cells, A/B stats that survive other writers | #bugfix #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-42 | 2026-09-24 | Data formats: workbook cells stay data, strict JSON Patch / JSONPath, ICU offsets and quoting, subtree ignores, safer masking and parsing | #bugfix #audit #security | [2026-09-b](2026-09-b.md) |
| U-20260924-41 | 2026-09-24 | Time and statistics: bounded sequence tracking, SLO window ends at now, local UNTIL, sane digests and outlier scores | #bugfix #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-40 | 2026-09-24 | Governance and supply chain: parsed license expressions, version-exact VEX, case-folded approvers, newline-proof traceparent | #bugfix #audit #security #supply-chain | [2026-09-b](2026-09-b.md) |
| U-20260924-39 | 2026-09-24 | Code Quality back to green: recorder pacing typed for OpenCV's stubs, redaction key pattern renamed past bandit | #ci #typing | [2026-09-b](2026-09-b.md) |
| U-20260924-38 | 2026-09-24 | HTTP family: egress matches the connected host, bounded bodies and decompression, safe multipart, RFC-correct Link and URL handling | #bugfix #audit #security #http | [2026-09-b](2026-09-b.md) |
| U-20260924-37 | 2026-09-24 | Process, secret and file boundaries: links recycled not targets, base-relative secret refs, batch-file arguments, fuller log redaction | #bugfix #audit #security | [2026-09-b](2026-09-b.md) |
| U-20260924-36 | 2026-09-24 | Queues and durable state: numbered claims, failed resumable steps retried, releasable idempotency keys, thread-safe dedup and outbox | #bugfix #audit #queue | [2026-09-b](2026-09-b.md) |
| U-20260924-35 | 2026-09-24 | Agent requests time out and resend only recent screenshots; empty tool filters, empty plans and stray VLM coordinates refused | #bugfix #audit #agent #llm #vision | [2026-09-b](2026-09-b.md) |
| U-20260924-34 | 2026-09-24 | Computer use: sent under its beta, bounded scrolls and waits, scroll at the model's coordinate | #bugfix #audit #agent | [2026-09-b](2026-09-b.md) |
| U-20260924-33 | 2026-09-24 | CLI: -d runs files in sorted order inside the directory only, the legacy entry point explains failures, dry-run vars, validate, failed suites, start-server port; pytest plugin robustness | #bugfix #audit #cli | [2026-09-b](2026-09-b.md) |
| U-20260924-32 | 2026-09-24 | Screen recordings play back at their real length; unusable writers are refused; iOS find_element honours its timeout | #bugfix #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-31 | 2026-09-24 | Executor: AC_run_dag expanded once, nested AC_execute_action inherits strictness, every repeated or unwound action keeps its record | #bugfix #audit #executor | [2026-09-b](2026-09-b.md) |
| U-20260924-30 | 2026-09-24 | AC_parallel branches inherit strictness, macro depth and failure counting; string branches are validated before anything runs | #bugfix #audit #executor | [2026-09-b](2026-09-b.md) |
| U-20260924-29 | 2026-09-24 | Versioned store keeps its high-water marks and locks CAS; config-bundle import copies before writing; cassettes redact credentials and check match fields | #bugfix #security #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-28 | 2026-09-24 | JWT codec: strict base64url, every malformed token a JwtError, NaN expiry refused, alg not overridable | #security #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-27 | 2026-09-24 | Admin console: no token on redirects, whole-request timeout and size cap, unknown labels reported, host files kept intact; USB viewer reassembly capped | #security #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-26 | 2026-09-24 | USB passthrough ACL: a deleted signature fails closed, damaged files are kept aside, rule ids are validated, instances stop overwriting each other | #security #audit #usb | [2026-09-b](2026-09-b.md) |
| U-20260924-25 | 2026-09-24 | Plugin discovery loads only the je_auto_control.commands entry-point group | #security #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-24 | 2026-09-24 | Masked, sub-pixel, auto-threshold and scale matchers answer in screen coordinates; golden images capture in mouse coordinates | #bugfix #audit #vision | [2026-09-b](2026-09-b.md) |
| U-20260924-23 | 2026-09-24 | Remote desktop stores keep damaged files aside; interrupted uploads are cleaned up; stopping the relay ends its sessions | #bugfix #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-22 | 2026-09-24 | Remote desktop host: failed logins free their slot, view-only means view-only, an allowlist of typos admits nobody | #security #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-21 | 2026-09-24 | Socket server reads whole pretty-printed commands; the documented client example works | #bugfix #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-20 | 2026-09-24 | MCP HTTP: anonymous initialize floods cannot evict a session in use; DELETE checks its path; state of a session dropped mid-request is released | #security #audit #mcp | [2026-09-b](2026-09-b.md) |
| U-20260924-19 | 2026-09-24 | REST API: authenticate before reading the body, never lock out the valid token, survive a corrupt audit database | #security #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-18 | 2026-09-24 | User store keeps a damaged file and refuses shared tokens; secret managers stop overwriting each other; malformed vaults are store errors | #security #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-17 | 2026-09-24 | Audit hash chain: no re-blessing of cleared hashes, deletions from the top caught, clear() leaves a record | #security #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-16 | 2026-09-24 | Signed-action enforcement covers remote DAG nodes; UserAuthError and CredentialBrokerError join the framework family | #security #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-15 | 2026-09-24 | Signing, encryption and JWT keys, passwords and tokens are masked in the executor log, its record and the MCP audit file | #security #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-14 | 2026-09-24 | Replay scrolls the recorded way on X11/Wayland, releases where the button went down; paths round; NaN holds refused | #bugfix #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-13 | 2026-09-24 | macOS and Linux hotkeys stop retrying a failed combo every tick; bind() validates on macOS | #bugfix #audit #macos #linux | [2026-09-b](2026-09-b.md) |
| U-20260924-12 | 2026-09-24 | Webhook server: chunked bodies, case-insensitive Bearer, and an answer when run history fails | #bugfix #audit #security | [2026-09-b](2026-09-b.md) |
| U-20260924-11 | 2026-09-24 | Trigger engine skips triggers removed mid-pass; poll threads survive infinite intervals and any rule error; callback executor returns its documented None | #bugfix #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-10 | 2026-09-24 | Email triggers: a failing script fires once, IMAP connections time out, unknown charsets keep their body | #bugfix #audit | [2026-09-b](2026-09-b.md) |
| U-20260924-09 | 2026-09-24 | Step videos from a generator, one-string trajectory rubrics, and the error type in failure bundles | #bugfix #audit | [2026-09](2026-09.md) |
| U-20260924-08 | 2026-09-24 | Codegen: every name compiles, NaN/Infinity survive, execute_action keeps its arguments, wrapped files and Robot names | #bugfix #audit #codegen | [2026-09](2026-09.md) |
| U-20260924-07 | 2026-09-24 | Rate limiters and retry budgets refuse NaN; LoopGuard is thread-safe; no repair tactics for a negative budget | #bugfix #audit | [2026-09](2026-09.md) |
| U-20260924-06 | 2026-09-24 | Scheduler: cron jobs no longer refire every tick in the repeated DST hour; a removed job's run leaves its successor alone | #bugfix #audit | [2026-09](2026-09.md) |
| U-20260924-05 | 2026-09-24 | JSON Schema validator: invalid regex, sub-schema $ref cycles, $ref siblings, nested const, exact multipleOf | #bugfix #audit | [2026-09](2026-09.md) |
| U-20260924-04 | 2026-09-24 | Action and .env files saved with a UTF-8 BOM run, lint and load | #bugfix #windows | [2026-09](2026-09.md) |
| U-20260924-03 | 2026-09-24 | A NaN timeout is refused instead of polling forever | #bugfix #audit | [2026-09](2026-09.md) |
| U-20260924-02 | 2026-09-24 | System utilities: Windows shell quoting, keep-awake, clipboard leaks, file triggers, waits, dotenv | #bugfix #windows #audit | [2026-09](2026-09.md) |
| U-20260924-01 | 2026-09-24 | Security floors: zeroconf 0.149.16 for discovery, and a test pinning every floor | #security #deps | [2026-09](2026-09.md) |
| U-20260923-54 | 2026-09-23 | Signaling guard keyed on the routed path (Starlette BadHost, CVE-2026-48710) | #security #remote_desktop #deps | [2026-09](2026-09.md) |
| U-20260923-53 | 2026-09-23 | Signaling server serves the config-sync bucket routes | #feature #remote_desktop #config_sync | [2026-09](2026-09.md) |
| U-20260923-52 | 2026-09-23 | Server-surface audit: signaling secret checked before the body, bearer scheme case | #incident #security #remote_desktop | [2026-09](2026-09.md) |
| U-20260923-51 | 2026-09-23 | Split the pure UIA reads out of windows_backend.py | #refactor #accessibility | [2026-09](2026-09.md) |
| U-20260923-50 | 2026-09-23 | Record / replay and input-helper audit: positions, held keys, speed, unknown ops, key names | #incident #input | [2026-09](2026-09.md) |
| U-20260923-49 | 2026-09-23 | Orchestration-runner audit: sagas that never rolled back, device matrix, DAG, work queue, observer | #incident #orchestration | [2026-09](2026-09.md) |
| U-20260923-48 | 2026-09-23 | Observability and report-output audit: OTLP spans, Prometheus, SARIF, purls, version ordering, step videos | #incident #observability | [2026-09](2026-09.md) |
| U-20260923-47 | 2026-09-23 | File-store audit: lost saves, assets without db, bundle entries, permissions, non-ASCII recall | #incident #storage #security | [2026-09](2026-09.md) |
| U-20260923-46 | 2026-09-23 | Plugin-loading audit: broken files, dataclass plugins, built-in overrides, watcher ownership | #incident #plugins #security | [2026-09](2026-09.md) |
| U-20260923-45 | 2026-09-23 | Resilience-primitive audit: backoff caps, rate limits, Retry-After, loop guard, leases, approvals, CAS, breaker | #incident #resilience #security | [2026-09](2026-09.md) |
| U-20260923-44 | 2026-09-23 | Text and clipboard-format audit: fuzzy autojunk, RTF Unicode, drop lists, pseudo-localization, slugify | #incident #text #clipboard | [2026-09](2026-09.md) |
| U-20260923-43 | 2026-09-23 | Image-utility audit: BGR/RGB grayscale, red colour matching, non-ASCII paths, approval extension | #incident #vision #security | [2026-09](2026-09.md) |
| U-20260923-42 | 2026-09-23 | QA subsystem audit: setup failures in reports, soft asserts, dead servers, malformed cases | #incident #qa | [2026-09](2026-09.md) |
| U-20260923-41 | 2026-09-23 | Executor flow-control audit: strictness through nested bodies, try/retry catch sets, double expansion | #incident #executor #security | [2026-09](2026-09.md) |
| U-20260923-40 | 2026-09-23 | dotenv, VEX, data-source and HTTP-header parsing audit | #incident #data #security | [2026-09](2026-09.md) |
| U-20260923-39 | 2026-09-23 | JSON Patch, JSONPath and unified-diff audit: bounds, shared values, silent wildcards, -U0 hunks | #incident #data | [2026-09](2026-09.md) |
| U-20260923-38 | 2026-09-23 | MCP tool-safety audit: annotations, read-only writes, resource reads, undeclared arguments | #incident #security #mcp | [2026-09](2026-09.md) |
| U-20260923-37 | 2026-09-23 | Secret detection and failure-bundle audit: key words, free text, vault commands, image modes | #incident #security #redaction | [2026-09](2026-09.md) |
| U-20260923-36 | 2026-09-23 | Accessibility / OCR / window audit: blank matches, wrong windows, zero timeouts | #incident #accessibility #window | [2026-09](2026-09.md) |
| U-20260923-35 | 2026-09-23 | Android/iOS audit: adb shell injection, escaping SDK errors | #incident #security #mobile | [2026-09](2026-09.md) |
| U-20260923-34 | 2026-09-23 | Wrapper audit: template-match accuracy, drawn multi-match, multi-monitor scroll, ctypes truncation | #incident #wrapper #image | [2026-09](2026-09.md) |
| U-20260923-33 | 2026-09-23 | Agent audit: broken computer-use actions, unoffered tools, VLM errors | #incident #security #agent | [2026-09](2026-09.md) |
| U-20260923-32 | 2026-09-23 | Circuit-breaker trials, config-sync and ACME error handling | #incident #resilience | [2026-09](2026-09.md) |
| U-20260923-31 | 2026-09-23 | Logic-engine audit: DAG failures, FSM guards and timers, RRULE semantics, suite variables | #incident #executor | [2026-09](2026-09.md) |
| U-20260923-30 | 2026-09-23 | Remote-desktop robustness: dead receive threads, blocked accept thread, signaling errors | #incident #remote-desktop | [2026-09](2026-09.md) |
| U-20260923-29 | 2026-09-23 | Codegen injection, USB/IP device scope, TLS key writes, signaling and relay limits | #incident #security | [2026-09](2026-09.md) |
| U-20260923-28 | 2026-09-23 | Shared JSON stores lock and re-read across processes | #done #stores | [2026-09](2026-09.md) |
| U-20260923-27 | 2026-09-23 | CLI / hotkey / recording audit: exit codes, lost recordings, wrong virtual keys | #incident #cli #hotkey | [2026-09](2026-09.md) |
| U-20260923-26 | 2026-09-23 | JSON store audit: in-place rewrites, constructor crashes, lost counts and log lines | #incident #stores | [2026-09](2026-09.md) |
| U-20260923-25 | 2026-09-23 | SQLite store audit: stuck work items, dedupe race, leaked connections, audit chain | #incident #stores | [2026-09](2026-09.md) |
| U-20260923-24 | 2026-09-23 | Outbound audit: credentials across redirects, egress bypass, chat-ops screenshot path | #incident #security #chatops | [2026-09](2026-09.md) |
| U-20260923-23 | 2026-09-23 | File transfer / admin audit: partial files, size limits, device names, poll crash | #incident #security #remote-desktop | [2026-09](2026-09.md) |
| U-20260923-22 | 2026-09-23 | Data-command audit: escaping errors, redirect egress bypass, Windows shell quoting | #incident #security #executor | [2026-09](2026-09.md) |
| U-20260923-21 | 2026-09-23 | Report audit: control characters, silent write failures | #incident #reports | [2026-09](2026-09.md) |
| U-20260923-20 | 2026-09-23 | CI actions moved off the deprecated Node 20 runtime | #ci #maintenance | [2026-09](2026-09.md) |
| U-20260923-19 | 2026-09-23 | Secret handling: masked passphrases in logs, atomic vault rekey, unique backups | #incident #security #secrets | [2026-09](2026-09.md) |
| U-20260923-18 | 2026-09-23 | Action signing audit: enforcement on every run path, key files, salted passphrases | #incident #security #signing | [2026-09](2026-09.md) |
| U-20260923-17 | 2026-09-23 | Scheduler/trigger audit: cron semantics, leap-day refire, lost edges | #incident #scheduler #triggers | [2026-09](2026-09.md) |
| U-20260923-16 | 2026-09-23 | MCP/REST audit: cross-session confirm, browser CSRF, token crash | #incident #security #mcp | [2026-09](2026-09.md) |
| U-20260923-15 | 2026-09-23 | USB passthrough audit: ACL bypasses, credit stall, claim leaks | #incident #security #usb | [2026-09](2026-09.md) |
| U-20260923-14 | 2026-09-23 | WebRTC host audit: approval without token, dead sessions | #incident #security #remote-desktop | [2026-09](2026-09.md) |
| U-20260923-13 | 2026-09-23 | Flow-control audit: seven defects reproduced and fixed | #incident #executor | [2026-09](2026-09.md) |
| U-20260923-12 | 2026-09-23 | Complexity limit measured in CI; the one function over it split | #done #quality | [2026-09](2026-09.md) |
| U-20260923-11 | 2026-09-23 | The 750-line limit is now a gate, and it caught one | #done #quality | [2026-09](2026-09.md) |
| U-20260923-10 | 2026-09-23 | Review follow-ups: priming race, stub width, key-table contract | #done #review | [2026-09](2026-09.md) |
| U-20260923-09 | 2026-09-23 | _handlers.py under the line limit: nine themed modules | #done #mcp | [2026-09](2026-09.md) |
| U-20260923-08 | 2026-09-23 | Import no longer sets the root logger to DEBUG | #done #logging | [2026-09](2026-09.md) |
| U-20260923-07 | 2026-09-23 | Tests get their own home; no state path resolved at import | #done #testing #state | [2026-09](2026-09.md) |
| U-20260923-06 | 2026-09-23 | Test runs no longer write the shared package log | #incident #logging #testing | [2026-09](2026-09.md) |
| U-20260923-05 | 2026-09-23 | Line limit enforced by ruff; stub regenerated (199 → 739) | #done #quality #typing | [2026-09](2026-09.md) |
| U-20260923-04 | 2026-09-23 | Pillow getdata → get_flattened_data (removed in Pillow 14) | #migration #deps | [2026-09](2026-09.md) |
| U-20260923-03 | 2026-09-23 | Every swallowing broad except says why; AST gate in CI | #done #quality | [2026-09](2026-09.md) |
| U-20260923-02 | 2026-09-23 | USB watcher: a stopped (not superseded) run still primes | #incident #usb #ci | [2026-09](2026-09.md) |
| U-20260923-01 | 2026-09-23 | Log file out of the cwd: home default, JE_AUTOCONTROL_LOG_FILE | #done #logging | [2026-09](2026-09.md) |
| U-20260922-16 | 2026-09-22 | Dependabot S-11: pypdf floor, direct pillow floor, lock refresh | #incident #security #deps | [2026-09](2026-09.md) |
| U-20260922-15 | 2026-09-22 | Windows key table: `down` is VK_DOWN; touchpad wheel accumulates | #incident #input #recording | [2026-09](2026-09.md) |
| U-20260922-14 | 2026-09-22 | Scheduler: never start a job that is still running | #incident #scheduler | [2026-09](2026-09.md) |
| U-20260922-13 | 2026-09-22 | Remote desktop host/relay/viewer: per-run events on restart | #incident #remote-desktop | [2026-09](2026-09.md) |
| U-20260922-12 | 2026-09-22 | 16 background services: a restart no longer revives the old loop | #incident #threading | [2026-09](2026-09.md) |
| U-20260922-11 | 2026-09-22 | Map §7: coverage floor 81, mypy exemptions 0 | #docs | [2026-09](2026-09.md) |
| U-20260922-10 | 2026-09-22 | CI: drop dead dev/stable triggers, delete duplicate dev.yml | #done #ci | [2026-09](2026-09.md) |
| U-20260922-09 | 2026-09-22 | CHANGELOG: one section per released version | #done #docs | [2026-09](2026-09.md) |
| U-20260922-08 | 2026-09-22 | Docs caught up: GUI launch, window platforms, CI jobs | #done #docs | [2026-09](2026-09.md) |
| U-20260922-07 | 2026-09-22 | Cross-project contract test: legacy CLI and consumer names (X-7) | #done #contracts | [2026-09](2026-09.md) |
| U-20260922-06 | 2026-09-22 | USB watcher: stop outlasts enumeration, restart can't revive | #incident #usb | [2026-09](2026-09.md) |
| U-20260922-05 | 2026-09-22 | Split QA adapters out of _handlers.py (4,791 → 4,389) | #done #mcp | [2026-09](2026-09.md) |
| U-20260922-04 | 2026-09-22 | Line-count gate: 71 map rows were never measured | #incident #docs | [2026-09](2026-09.md) |
| U-20260922-03 | 2026-09-22 | hotkey/type_keyboard release held keys on failure | #incident #input | [2026-09](2026-09.md) |
| U-20260922-02 | 2026-09-22 | Windows recorder captures mouse side buttons (x1/x2) | #incident #recording | [2026-09](2026-09.md) |
| U-20260922-01 | 2026-09-22 | Adopt progress/architecture/docs-updates rules | #docs #migration | [2026-09](2026-09.md) |
| U-20260824-02 | 2026-08-24 | Coverage ratchet: target 80 met, floor 81 (Progress.md) | #migration #coverage | [2026-08-f](2026-08-f.md) |
| U-20260824-01 | 2026-08-24 | Coverage floor 81: backend doubles and the bugs they found | #release #coverage #testing | [2026-08-e](2026-08-e.md) |
| U-20260823-01 | 2026-08-23 | Adapter sweep: test stubs built from the typing contract | #release #coverage #typing | [2026-08-e](2026-08-e.md) |
| U-20260822-01 | 2026-08-22 | mypy typing contract: exemption list emptied (Progress.md) | #migration #typing | [2026-08-d](2026-08-d.md) |
| U-20260821-01 | 2026-08-21 | Typing contract covers whole package; coverage re-measured | #release #typing #coverage | [2026-08-d](2026-08-d.md) |
| U-20260820-01 | 2026-08-20 | Platform matrix measured; window management off Windows | #release #platforms #ci | [2026-08-c](2026-08-c.md) |
| U-20260819-02 | 2026-08-19 | Wayland: answered questions and distro facts (Progress.md) | #migration #wayland #ci | [2026-08-b](2026-08-b.md) |
| U-20260819-01 | 2026-08-19 | Wayland seat, portal and ydotool verified against real peers | #release #wayland #ci | [2026-08-b](2026-08-b.md) |
| U-20260818-01 | 2026-08-18 | libei input end to end; Wayland capture on a real compositor | #release #wayland #libei | [2026-08](2026-08.md) |
| U-20260817-01 | 2026-08-17 | Wayland screen capture and window-owner lookup | #release #wayland #windows | [2026-08](2026-08.md) |
| U-20260815-01 | 2026-08-15 | Unicode typing, replayable recordings, clipboard images | #release #input #clipboard | [2026-08](2026-08.md) |
| U-20260718-01 | 2026-07-18 | Cross-platform reliability hardening, no API changes | #release #reliability | [2026-07](2026-07.md) |
| U-20260703-01 | 2026-07-03 | Stable API facade, failure bundles, tag-based releases | #release #api #packaging | [2026-07](2026-07.md) |
| U-20260702-01 | 2026-07-02 | GUI Actions menu replaces in-tab buttons | #release #gui | [2026-07](2026-07.md) |
| U-20260626-01 | 2026-06-26 | Trial/force modes, element proposal, idle and state waits | #release #actions #vision | [2026-06-c](2026-06-c.md) |
| U-20260625-01 | 2026-06-25 | UIA control patterns, default-app launch, run-trace diff | #release #uia #reporting | [2026-06-b](2026-06-b.md) |
| U-20260624-01 | 2026-06-24 | Template-matching variants, UIA text and OCR layout tools | #release #vision #uia #ocr | [2026-06-b](2026-06-b.md) |
| U-20260623-01 | 2026-06-23 | Matching, window geometry, Unicode input and wait primitives | #release #vision #window #input | [2026-06-b](2026-06-b.md) |
| U-20260622-01 | 2026-06-22 | i18n, idempotency, time-series, HTTP and config utilities | #release #i18n #http #data | [2026-06-b](2026-06-b.md) |
| U-20260621-01 | 2026-06-21 | Tracing, data profiling, JSON/JWT and supply-chain gates | #release #observability #data #security | [2026-06](2026-06.md) |
| U-20260620-01 | 2026-06-20 | SARIF export, PII redaction, sagas, webhooks, asset store | #release #security #integration | [2026-06](2026-06.md) |
| U-20260619-01 | 2026-06-19 | Agent observability, compliance reports, approvals, SDK | #release #agent #compliance | [2026-06](2026-06.md) |
| U-20260618-01 | 2026-06-18 | CLI, recording-to-code, HTTP/SQL/email/PDF steps, waits | #release #cli #integration | [2026-06](2026-06.md) |
| U-20260617-01 | 2026-06-17 | Humanized input, macros, parallel runs, cron, file signing | #release #input #flow-control | [2026-06](2026-06.md) |
| U-20260605-01 | 2026-06-05 | QA framework: assertions, data-driven runs, suites, flaky | #release #qa #testing | [2026-06](2026-06.md) |
| U-20260525-01 | 2026-05-25 | Self-healing locators, Wayland/Android/iOS, agent loop | #release #locators #platforms #agent | [2026-05](2026-05.md) |

## Batches

| File | Period | Entries |
|---|---|---:|
| [2026-09-d.md](2026-09-d.md) | 2026-09 | 10 |
| [2026-09-c.md](2026-09-c.md) | 2026-09 | 38 |
| [2026-09-b.md](2026-09-b.md) | 2026-09 | 68 |
| [2026-09.md](2026-09.md) | 2026-09 | 79 |
| [2026-08-f.md](2026-08-f.md) | 2026-08 | 1 |
| [2026-08-e.md](2026-08-e.md) | 2026-08 | 2 |
| [2026-08-d.md](2026-08-d.md) | 2026-08 | 2 |
| [2026-08-c.md](2026-08-c.md) | 2026-08 | 1 |
| [2026-08-b.md](2026-08-b.md) | 2026-08 | 2 |
| [2026-08.md](2026-08.md) | 2026-08 | 3 |
| [2026-07.md](2026-07.md) | 2026-07 | 3 |
| [2026-06-c.md](2026-06-c.md) | 2026-06 | 1 |
| [2026-06-b.md](2026-06-b.md) | 2026-06 | 4 |
| [2026-06.md](2026-06.md) | 2026-06 | 6 |
| [2026-05.md](2026-05.md) | 2026-05 | 1 |
