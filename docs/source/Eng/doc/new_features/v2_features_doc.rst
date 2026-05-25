============================
New Features (2026-05)
============================

Twenty-three additions covering smarter locators, deeper IDE / ops
tooling, two new platforms, and a couple of fresh integrations. Every
feature ships with a headless Python API, an ``AC_*`` executor
command, an ``ac_*`` MCP tool, and (where it makes sense) a Qt GUI
tab — same pattern as the rest of the framework.

.. contents::
   :local:
   :depth: 2


Locator + selector intelligence
===============================

Self-healing locator
--------------------

``image_template → VLM fallback`` with a JSON-lines audit log so flaky
locators can be tuned over time::

    from je_auto_control import self_heal_click

    outcome = self_heal_click(
        template_path="submit.png",
        description="the green Submit button",
    )

Executor: ``AC_self_heal_locate / _click / _log_list / _log_clear``.
MCP: ``ac_self_heal_*``. GUI: **Self-Healing** tab.


Anchor-based locator
--------------------

Find element B by spatial relation to anchor A. Anchor + target can use
different backends — pick the cheapest one that uniquely identifies
each part::

    from je_auto_control import (
        anchor_locate, image_locator, ocr_locator,
    )

    outcome = anchor_locate(
        anchor=ocr_locator("Username"),
        target=image_locator("submit_green.png"),
        relation="below",
    )

Relations: ``above``, ``below``, ``left_of``, ``right_of``, ``near``.
Executor: ``AC_anchor_locate / _click``.


OCR with structured output
--------------------------

Cluster raw OCR matches into rows, tables (sets of rows that share
column alignment), and form-field ``label:value`` pairs::

    from je_auto_control import ocr_read_structure
    result = ocr_read_structure(region=[0, 0, 1280, 800])
    for field in result.fields:
        print(field.label, "=", field.value)

Executor: ``AC_ocr_read_structure``.


Smart waits
-----------

Frame-diff replacements for ``time.sleep``::

    from je_auto_control import wait_until_screen_stable
    wait_until_screen_stable(timeout_s=10.0, stable_for_s=0.5)

Helpers: ``wait_until_screen_stable``, ``wait_until_pixel_changes``,
``wait_until_region_idle``. Executor: ``AC_wait_screen_stable``,
``AC_wait_pixel_changes``, ``AC_wait_region_idle``.


A/B locator framework
---------------------

Race N strategies for the same target and recommend the historically
best one::

    from je_auto_control import ab_locate, ab_best_strategy

    outcome = ab_locate(
        target_id="submit_button",
        strategies={
            "image": image_locator("submit.png"),
            "ocr": ocr_locator("Submit"),
            "vlm": vlm_locator("the green Submit button"),
        },
    )
    print("historical best:", ab_best_strategy("submit_button"))

Persistent ledger under ``~/.je_auto_control/ab_locator_stats.json``.
Executor: ``AC_ab_locate / _report / _best_strategy / _clear``.


Operations + observability
==========================

Cost telemetry
--------------

Per-call LLM token + USD log with day / model / provider roll-up::

    from je_auto_control import record_llm_call, summarise_llm_costs

    record_llm_call(
        provider="anthropic", model="claude-opus-4-7",
        input_tokens=512, output_tokens=128, label="vlm_locate",
    )
    summary = summarise_llm_costs()
    print(summary.total_usd, summary.by_model)

Pricing table covers Claude 4.x and OpenAI; override per-call.
Executor: ``AC_costs_record / _summary / _list / _clear``.


Trace replay UI
---------------

Scrubbable timeline over the existing time-travel recordings — load a
directory containing ``manifest.json`` + ``actions.jsonl`` and step
backwards through frames with the per-step action list alongside.
``TraceReplayController`` ships as a pure-Python class for non-GUI
use; the **Trace Replay** GUI tab is a thin shell on top.


Failure → ticket automation
---------------------------

Fan a failure report out to Jira / Linear / GitHub Issues when a
scheduled run, trigger, or REST job blows up::

    from je_auto_control import (
        FailureReport, GitHubBackend, default_failure_hook_manager,
    )
    default_failure_hook_manager.register(
        GitHubBackend(owner="acme", repo="ops",
                       token=os.environ["GH_TOKEN"]),
    )

Executor: ``AC_failure_hook_fire / _list / _clear``.


Container CI templates
----------------------

* ``.github/workflows/docker.yml`` — builds the image, runs the
  headless pytest suite inside it under Xvfb, smoke-tests the REST
  entrypoint.
* ``ci_templates/.gitlab-ci.yml`` — equivalent pipeline for GitLab
  via Docker-in-Docker.
* ``docker/Dockerfile.xfce`` — XFCE4 desktop + x11vnc variant for
  flows that need a real WM.

See ``docs/source/getting_started/run_in_ci.rst`` for the full guide.


Cross-host DAG orchestrator
---------------------------

Run a DAG where each node carries ``(host, actions | action_file,
depends_on)``. Local nodes execute in-process; remote nodes go through
the admin-console REST clients. Failures cascade — every downstream
node is reported as ``skipped`` instead of attempted::

    je_auto_control.run_dag({
        "nodes": [
            {"id": "step1", "host": "local", "actions": [...]},
            {"id": "step2", "host": "machine-a",
             "action_file": "x.json", "depends_on": ["step1"]},
        ],
    })

Executor: ``AC_run_dag``. GUI: **DAG Runner** tab.


Multi-viewer presence
---------------------

Roster + controller / observer roles for the multi-viewer remote
desktop. Pure-Python ``PresenceRegistry`` ships independently so
input-dispatch gating can be unit-tested without aiortc.

Executor: ``AC_presence_register / _unregister / _update_cursor /
_set_role / _list / _clear``. GUI: **Viewer Roster** tab.


Agent + integrations
====================

Computer-use high-level API
---------------------------

Wraps :class:`ComputerUseAgentBackend` + :class:`AgentLoop` so a
single call drives Anthropic's official ``computer_20250124`` tool::

    from je_auto_control import run_computer_use
    result = run_computer_use(
        "open Calculator, compute 12 * 7, screenshot the result",
        max_steps=15, wall_seconds=120.0,
    )

Auto-detects display size; takes ``max_steps`` + ``wall_seconds``
budgets so a runaway loop can't drain the API. Executor:
``AC_computer_use``. GUI: **Computer Use** tab.


WebRunner executor + MCP integration
------------------------------------

Brand-new convenience commands on top of the existing
``je_web_runner`` bridge::

    je_auto_control.web_open("https://example.com")
    je_auto_control.web_screenshot("loaded.png")
    je_auto_control.web_quit()

Executor: ``AC_web_open / _quit / _screenshot / _current_url``
(joining the existing ``AC_web_run``). MCP exposes the same surface
as ``ac_web_*``. GUI: **WebRunner** tab.


Chat-ops bot
------------

Transport-agnostic ``CommandRouter`` plus a polling Slack adapter so
``/run <script>`` over Slack hits the same execution path as the
scheduler. Built-in commands: ``/help``, ``/scripts``, ``/run``,
``/screenshot``, ``/status``. RBAC via the ``required_role``
parameter. GUI: **Chat-Ops** playground tab.


Platform coverage
=================

Wayland CLI backend
-------------------

Drop-in Wayland backend that talks to ``wtype`` (keyboard text input),
``ydotool`` (key events + mouse), and ``grim`` (screenshots). Auto-detects
``XDG_SESSION_TYPE=wayland`` / ``WAYLAND_DISPLAY`` at import time and
falls back to X11 (XWayland) when the CLI helpers aren't installed.

Override::

   export JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11      # force XWayland
   export JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=wayland  # force Wayland
   export JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=auto     # default


Wayland libei native backend
----------------------------

ctypes binding to ``libei.so.*`` that bypasses the CLI shims for
microsecond-latency input. Opt-in via
``JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=libei|cli|auto``; the
``auto`` default uses libei when loadable and CLI otherwise, so
existing deployments keep working.


macOS Accessibility: tree dump + recorder
-----------------------------------------

Extends the macOS AX backend with a recursive tree dump
(``dump_accessibility_tree()``) and a polling event recorder
(``AccessibilityRecorder``) that captures focus / bounds changes.

Executor: ``AC_a11y_dump``, ``AC_a11y_record_start / _stop /
_events``.


Developer experience
====================

autocontrol-lsp completion
--------------------------

The language server now tracks documents (``didOpen`` /
``didChange`` / ``didClose``), publishes diagnostics for invalid JSON
and unknown ``AC_*`` commands, and provides signature help generated
from the live ``Executor.event_dict``. Schema validation flags
unknown commands and malformed action lists before runtime.


``.pyi`` stub generator
-----------------------

Run::

   python -m je_auto_control.utils.stubs.generator \
       je_auto_control/actions.pyi

to refresh the IDE-facing stub. IDEs (PyCharm, VS Code via Pylance,
Pyright) pick it up via the standard ``actions.pyi`` lookup so every
``AC_*`` command autocompletes with parameter hints.


VS Code extension
-----------------

The bundled extension under ``autocontrol-lsp/vscode/`` now also
exposes three commands::

   AutoControl: Run current script via REST API
   AutoControl: Take screenshot (REST API)
   AutoControl: Preview script as step tree

REST URL + bearer token come from VS Code settings
(``autocontrolLsp.rest.url`` / ``autocontrolLsp.rest.token``) with
``$AC_TOKEN`` as a fallback.


Browser extension recorder
--------------------------

Manifest V3 extension under ``browser-extension/`` that captures
clicks, typing, navigation, and form submissions in a browser tab
and exports them as an AutoControl JSON action file driveable by
``AC_web_*`` / ``WR_*``. CSS selectors fall back to
``data-testid`` / ``data-cy`` / ``name`` / ``nth-of-type`` paths,
mirroring how production-style locators are typically picked.


pytest plugin + Gherkin BDD
---------------------------

Installing ``je_auto_control`` now registers a ``pytest11`` entry
point, so the plugin loads automatically. Fixtures
(``autocontrol``, ``autocontrol_executor``,
``autocontrol_screenshot_dir``) and a
``@pytest.mark.autocontrol`` marker arm a screenshot-on-failure
hook. ``bdd_steps.register_pytest_bdd_steps(pytest_bdd)`` wires
``Given / When / Then`` step templates onto every public ``AC_*``
verb.


Visual flow editor
------------------

Node-based view of an AC JSON script. Round-trips to the same JSON
format the list-based **Script Builder** uses, so the two views stay
compatible. The pure-Python layout helper
(``je_auto_control.gui.flow_editor.layout_steps``) is unit-tested
without Qt.


Generic agent loop (JSON + MCP)
-------------------------------

``AC_run_agent`` / ``ac_run_agent`` expose the closed-loop
``AgentLoop`` (plan → act → verify → retry) to the JSON action
language and the MCP tool registry. Parameters:

* ``goal`` — natural-language objective.
* ``backend`` — ``"anthropic"`` (uses ``export_anthropic_tools()``
  with tool-use messages) or ``"openai"`` (uses ``export_openai_tools()``
  with Chat Completions function calling).
* ``max_steps`` (default 25) and ``wall_seconds`` (default 300.0).
* ``model`` / ``max_tokens`` — backend-specific overrides.

The Anthropic-only Computer-Use raw path (``computer_20250124``) is
still available via ``AC_computer_use`` / ``ac_computer_use`` and is
the right choice when the agent needs to drive a desktop the model
itself sees pixel-for-pixel.


Screenshot PII redaction
------------------------

The new ``je_auto_control.utils.redaction`` package introduces a
``RedactionEngine`` plus three pre-baked policies
(``POLICY_OFF / MODERATE / STRICT``). Built-in detectors:

* Regex against caller-supplied OCR tokens — email, credit card,
  SSN, phone.
* Accessibility-tree secure-text-entry fields (the engine reads
  ``[{"is_password": True, "bbox": [x1, y1, x2, y2]}, ...]`` from
  ``context["accessibility"]``).
* Forced regions for sticky overlays the rules cannot see.

The default policy is resolved from ``JE_AUTOCONTROL_REDACTION``
(``off`` / ``moderate`` / ``strict``). Per-call control:

.. code-block:: python

   from je_auto_control import redact_png_bytes, POLICY_STRICT
   redacted_bytes, result = redact_png_bytes(png_bytes, policy=POLICY_STRICT)

Wired through ``AC_redact_screenshot`` and ``ac_redact_screenshot``,
which read PNG bytes from disk, run the engine, and write the
redacted image to ``output_path`` (or overwrite the source). The
return value lists the merged bounding boxes for audit.


Android backend (uiautomator2 widget tree)
------------------------------------------

Adds widget-aware automation on top of the existing
``AC_android_tap / swipe / key / text / screenshot`` adb-shell path:

* ``AC_android_find_element`` — select by ``text`` /
  ``resource_id`` / ``description`` / ``class_name``. Returns
  ``{x1, y1, x2, y2}``.
* ``AC_android_click_element`` — same selectors, taps the centre,
  returns ``{x, y}``.
* ``AC_android_dump_hierarchy`` — live XML widget tree.

``je_auto_control/android/client.py`` exposes ``UIAutomatorDevice``
as the Python entry point, with optional ``serial`` selection for
multi-device rigs. ``uiautomator2`` is a lazy optional dependency.


iOS backend (XCUITest via WebDriverAgent)
-----------------------------------------

New ``je_auto_control.ios`` namespace with:

* ``tap`` / ``long_press`` / ``swipe`` / ``type_text`` /
  ``press_key`` — touch + key primitives.
* ``screenshot`` / ``screen_size`` — capture + bounds.
* ``find_element`` / ``click_element`` — selector by ``name``
  (label / accessibility id), ``class_name``
  (``XCUIElementTypeButton`` …), or full ``predicate``
  (NSPredicate string).
* ``dump_source`` — XCUITest page source XML.

Seven new ``AC_ios_*`` executor commands and matching ``ac_ios_*``
MCP tools. ``facebook-wda`` is a lazy optional dependency; importing
``je_auto_control.ios`` on a non-Mac host does not fail.
