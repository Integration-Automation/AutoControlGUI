==================================
New Features (2026-06) — QA Layer
==================================

Nine additions that turn AutoControl's automation primitives into a
full **test framework**: assert screen state, drive scripts from data,
detect and quarantine flaky tests, run a scored suite, emit CI-native
reports, audit accessibility / i18n, fan a script across a device
matrix, and assert on audio / video. Every feature ships with a
headless Python API, an ``AC_*`` executor command, an ``ac_*`` MCP
tool, and a Qt GUI tab — same pattern as the rest of the framework.

.. contents::
   :local:
   :depth: 2


Assertions
==========

Assertion DSL
-------------

Verify the screen state instead of only driving it. Each ``assert_*``
observes the current state, returns an :class:`AssertionResult`, and
(by default) raises ``AutoControlAssertionException`` on mismatch so a
script / test / scheduled run fails loudly at the broken assumption::

    from je_auto_control import (
        assert_text, assert_image, assert_pixel, assert_window,
    )

    assert_text("Login successful", region=[0, 0, 800, 200])
    assert_image("checkmark.png", threshold=0.9)
    assert_pixel(100, 200, [0, 200, 0], tolerance=10)
    assert_window("Settings", exists=True)

``assert_text`` accepts ``regex=True`` and ``present=False`` (assert
*absence*); every helper takes ``raise_on_fail`` and ``capture_on_fail``
(saves a screenshot of the failing screen under
``~/.je_auto_control/assertions/``).

Executor: ``AC_assert_text / _image / _pixel / _window``.
MCP: ``ac_assert_*``. GUI: **Assertions** tab.


Off-screen and system assertions
---------------------------------

The DSL also verifies state that is not on the screen::

    from je_auto_control import (
        assert_clipboard, assert_process, assert_file, assert_http,
    )

    assert_clipboard("ORDER-12345", mode="contains")
    assert_process("chrome", running=True)
    assert_file("export.csv", min_size=1, contains="total")
    assert_http("https://localhost:8080/health", status=200)

* ``assert_clipboard`` — clipboard text by ``equals`` / ``contains`` /
  ``regex``; ``present=False`` confirms a secret was *cleared*.
* ``assert_process`` — a process whose name contains the argument is (or
  is not) running, via ``psutil``.
* ``assert_file`` — existence / substring / SHA-256 / minimum size of a
  file; the path is ``realpath``-normalised before any I/O. Verifies a
  download or export.
* ``assert_http`` — an ``http``/``https`` endpoint returns a status code
  (and optional body substring), always with an explicit ``timeout``.
  Only ``http``/``https`` schemes are accepted; an unreachable host is a
  failed assertion, not a crash.

Executor: ``AC_assert_clipboard / _process / _file / _http``.
MCP: ``ac_assert_clipboard / ac_assert_process / ac_assert_file /
ac_assert_http``.


Assertion combinators (group / OR / poll)
-----------------------------------------

Compose the eight assertion kinds with declarative *specs* — plain dicts
like ``{"kind": "text", "text": "Saved"}`` — so the same checks are
reachable from Python, JSON, and MCP without passing callables::

    from je_auto_control import assert_all, assert_any, assert_eventually

    # soft assertions: run the whole batch, collect every failure
    assert_all([
        {"kind": "window", "title": "Dashboard"},
        {"kind": "text", "text": "Welcome"},
    ])

    # OR: pass when at least one spec passes (short-circuits)
    assert_any([
        {"kind": "text", "text": "Success"},
        {"kind": "window", "title": "Redirecting"},
    ])

    # poll any spec until it passes or times out
    assert_eventually({"kind": "http", "url": "http://localhost:8080/health"},
                      timeout=30, interval=0.5)

``assert_all`` (AND) never short-circuits and returns a
:class:`GroupAssertionResult` summarising every sub-result;
``assert_any`` (OR) stops at the first pass; ``assert_eventually``
re-checks one spec on an interval until it holds — ideal for waiting on a
service to come up or a download file to appear.

Executor: ``AC_assert_all / AC_assert_any / AC_assert_eventually``.
MCP: ``ac_assert_all / ac_assert_any / ac_assert_eventually``.


Media assertions (audio / video)
--------------------------------

Assert that something actually *played* or *animated*::

    from je_auto_control import assert_audio_activity, assert_video_changes

    assert_audio_activity(duration_s=1.0, threshold=0.01, expect_sound=True)
    assert_video_changes("clip.mp4", start_s=0, end_s=3, expect_motion=True)

``assert_audio_activity`` records from an input device and compares the
RMS level to a threshold (sound vs silence). ``assert_video_changes``
measures mean frame-to-frame difference over a video segment (motion vs
static), with an optional ``region`` crop. The numeric cores
(``rms``, ``mean_frame_diff``, ``measure_audio_rms``,
``video_segment_motion``) are public and pure. ``sounddevice`` /
OpenCV are lazy dependencies.

Executor: ``AC_assert_audio / AC_assert_video_changes``.
MCP: ``ac_assert_audio / ac_assert_video_changes``. GUI: **Media
Checks** tab.


Data-driven execution
=====================

Feed rows from CSV / JSON / SQLite / Excel / inline literals into a
``${var}`` script, then run the same body once per row::

    from je_auto_control import load_rows

    rows = load_rows({"kind": "csv", "path": "users.csv"})

In a JSON action file the new ``AC_for_each_row`` block command loads a
data source and binds each row to a variable whose columns are
addressable as ``${row.column}``::

    ["AC_for_each_row", {
        "source": {"kind": "csv", "path": "users.csv"},
        "as": "row",
        "body": [
            ["AC_type_keyboard", {"keys": "${row.username}"}],
            ["AC_assert_text", {"text": "${row.expected}"}]
        ]
    }]

The SQLite connector accepts a **single read-only** ``SELECT`` / ``WITH``
statement only (multi-statement / write queries are rejected); all file
paths are ``realpath``-validated. ``${var}`` interpolation now resolves
dotted paths into dict keys and list indices (``${row.user}``,
``${results.0}``) while preserving value types.

Executor: ``AC_load_data`` + ``AC_for_each_row``.
MCP: ``ac_load_data``. GUI: **Data Sources** tab.


Flaky-test detection & quarantine
==================================

Flaky report
------------

Score intermittent failures from the SQLite run-history store. Runs are
grouped by ``script_path`` (or ``source_id``); the report counts
pass/fail outcomes and pass↔fail *flips* in chronological order so a
flaky script ranks above one that is consistently green or red::

    from je_auto_control import analyze_flakiness

    report = analyze_flakiness(min_runs=3)
    for entry in report.entries:
        print(entry.key, entry.flip_rate, entry.flaky)

Executor: ``AC_flaky_report``. MCP: ``ac_flaky_report``.
GUI: **Flaky Tests** tab.


Quarantine (closing the loop)
-----------------------------

A quarantined case name is *skipped* by the suite runner (recorded as
``skipped`` with reason ``quarantined``) so a known-flaky case stops
poisoning the suite's red/green status until it is fixed. The store is a
small JSON file (mode 0600 on POSIX) that persists across restarts::

    from je_auto_control import (
        default_quarantine_store, auto_quarantine_from_flakiness,
    )

    default_quarantine_store().add("login_suite", reason="under triage")
    auto_quarantine_from_flakiness(flip_rate_threshold=0.5)

``auto_quarantine_from_flakiness`` reads the flakiness report and
quarantines every group above the flip-rate threshold.

Executor: ``AC_quarantine_add / _remove / _list / _clear / _auto``.
MCP: ``ac_quarantine_*``. GUI: quarantine panel on the **Test Suites**
tab.


QA suite runner + CI reports
============================

Suite orchestration
-------------------

Turn flat action lists into scored test cases with setup / teardown,
tags, and per-case pass/fail. A case carrying a ``data`` source expands
to one scored case per row::

    from je_auto_control import run_suite

    spec = {
        "name": "Login",
        "setup":    [["AC_focus_window", {"title": "MyApp"}]],
        "teardown": [["AC_close_window", {"title": "MyApp"}]],
        "cases": [
            {"name": "valid login", "tags": ["smoke"],
             "actions": [["AC_assert_text", {"text": "Welcome"}]]},
            {"name": "each user", "as": "row",
             "data": {"kind": "csv", "path": "users.csv"},
             "actions": [["AC_assert_text", {"text": "${row.expected}"}]]},
        ],
    }
    result = run_suite(spec, tags=["smoke"])
    print(result.passed, result.failed, result.errored, result.skipped)

An ``AutoControlAssertionException`` marks a case **failed**; any other
exception marks it **error**; a clean run is **passed**. Quarantined
case names are recorded as **skipped**.

Executor: ``AC_run_suite``. MCP: ``ac_run_suite``.
GUI: **Test Suites** tab.


CI-native reports (JUnit / Allure)
----------------------------------

Emit reports that Jenkins, GitHub Actions, GitLab CI, and Allure parse
natively::

    from je_auto_control import write_junit_xml, write_allure_results

    write_junit_xml(result, "reports/junit.xml")
    write_allure_results(result, "reports/allure")

``AC_run_suite`` writes them inline when given ``junit_path`` /
``allure_dir``::

    ["AC_run_suite", {"spec": {...}, "junit_path": "reports/junit.xml"}]

Only report *generation* happens here (never parsing untrusted XML), so
the stdlib ``xml.etree.ElementTree`` writer is safe.


Accessibility & i18n audit
==========================

Reuse the accessibility tree and OCR layer to *inspect* a UI for common
accessibility / localisation defects rather than to drive it::

    from je_auto_control import run_audit, contrast_ratio

    report = run_audit(
        app_name="MyApp",
        contrast_pairs=[{"foreground": [120, 120, 120],
                         "background": [255, 255, 255], "label": "hint"}],
        texts=["Save chang…"],   # OCR strings to scan for truncation
    )

Checks:

* **Missing labels** — interactive widgets (button, menu item, link,
  field …) exposed through the a11y tree with no accessible name.
* **Contrast** — WCAG 2.x relative-luminance contrast ratio with AA /
  AAA thresholds (``contrast_ratio([0,0,0],[255,255,255]) == 21.0``).
* **Truncation** — OCR strings ending in an ellipsis (clipped after
  translation).

Executor: ``AC_audit_accessibility / AC_audit_contrast``.
MCP: ``ac_audit_*``. GUI: **A11y Audit** tab.


Mobile device matrix
====================

Fan a single action list out across many Android / iOS devices **in
parallel**, each on its own isolated executor (so runtime variable
scopes never collide between threads). The script targets the current
device through a bound ``${device.*}`` variable::

    from je_auto_control import run_on_devices

    report = run_on_devices(
        actions=[["AC_android_tap", {"x": 100, "y": 200,
                                     "serial": "${device.serial}"}]],
        devices=[{"platform": "android", "serial": "emulator-5554"},
                 {"platform": "android", "serial": "emulator-5556"}],
        max_parallel=4,
    )
    print(report.passed, report.failed)

A failure on one device is isolated — it never aborts the others.

Executor: ``AC_run_device_matrix``. MCP: ``ac_run_device_matrix``.
GUI: **Device Matrix** tab.
