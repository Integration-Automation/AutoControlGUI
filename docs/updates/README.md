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
| [2026-09.md](2026-09.md) | 2026-09 | 64 |
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
