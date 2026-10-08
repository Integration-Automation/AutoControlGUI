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

``screen_region`` is ``[x1, y1, x2, y2]`` in screen coordinates and confines
**both** strategies; it used to reach only the VLM, so the template match
could answer from outside the region.

**Located is not verified.** ``HealOutcome.found`` says a strategy returned a
point. Whether the click did what it was for is a separate field,
``action_verified``, filled from a check the caller passes — ``None`` when no
check ran, never inferred from the hit::

    outcome = self_heal_click(
        template_path="submit.png",
        description="the green Submit button",
        verify=lambda result: dialog_is_open(),
    )
    outcome.found            # a point was returned
    outcome.action_verified  # True / False from the check, None without one

Heal-log lines gained optional fields (``schema_version``, ``run_id``,
``step_id``, ``locator_id``, ``locator_version``, ``backend``, ``model``,
``screen_region``, ``image_ms``, ``vlm_ms``, ``action``, ``action_verified``).
Lines written before they existed still load, with those fields ``None``.
Stamp the ids from the caller's side::

    from je_auto_control import heal_context

    with heal_context(run_id="nightly-42", locator_id="submit", locator_version="v2"):
        self_heal_click(template_path="submit.png")

From a JSON action or MCP, pass the same keys as ``context`` on
``AC_self_heal_locate`` / ``AC_self_heal_click``.

A JSON step cannot carry a callable, so ``verify`` may also be an object —
on ``AC_self_heal_click``, on the ``ac_self_heal_click`` MCP tool, in the
Self-Healing tab's *Verify after click* field, and from Python::

    ["AC_self_heal_click", {
        "template_path": "submit.png",
        "verify": {"type": "image_gone", "timeout_s": 3}}]

==================  ==========================================================
``type``            holds when
==================  ==========================================================
``image_gone``      ``template_path`` (default: the clicked template) is no
                    longer found
``image_present``   ``template_path`` is found
``text_present``    the OCR engine reads ``text`` (``lang``,
                    ``min_confidence``, ``case_sensitive`` as for
                    ``find_text_matches``)
==================  ==========================================================

Common options: ``screen_region`` (``[x1, y1, x2, y2]``; default: the click's
own region), ``timeout_s`` (default 2, the check is repeated until it holds or
the time is up) and ``poll_s`` (default 0.2); image types also take
``detect_threshold`` (default 0.9). The object is validated before anything is
clicked — an unknown type or option raises ``HealVerificationError`` and no
click happens. A check that cannot be carried out (unreadable template, no OCR
engine, failed capture) raises the same error *after* the click and the event
is logged with ``action_verified`` ``None``: "could not look" is never
reported as "gone". Without ``verify`` the field stays ``None``.
``AC_heal_stats`` reports
``action_verification`` (``actions`` / ``verified`` / ``failed`` /
``unchecked``) apart from ``healed``, which only counts returned points.

Measuring locator versions
~~~~~~~~~~~~~~~~~~~~~~~~~~

``evaluate_locators`` runs every strategy version over the same labelled
frames — one captured frame, one region, one origin and scale per sample, the
same request object for every version — and scores the answers::

    from je_auto_control import (
        EvaluationSample, evaluate_locators, template_match_strategy,
    )

    samples = [
        EvaluationSample("submit", frame, expected_box=(100, 60, 156, 92),
                         template="submit.png"),
        EvaluationSample("left-monitor-150", hidpi_frame,
                         expected_box=(-1880, -180, -1824, -148),
                         origin=(-1920, -300), scale=1.5, template="submit.png"),
        EvaluationSample("dialog-closed", other_frame, expect_miss=True,
                         template="submit.png"),
    ]
    comparison = evaluate_locators(samples, {
        "v1": template_match_strategy(0.9),
        "v2": template_match_strategy(0.9, scales=(1.0, 1.25, 1.5, 2.0)),
    })
    report = comparison.report("v2")
    report.accuracy          # Ratio(numerator, denominator); .value is None over 0
    report.recovery_rate     # targets v1 failed on that v2 hit correctly
    report.p50_ms, report.p95_ms
    comparison.failures("v2")

How a result is counted:

* a hit inside ``expected_box`` is ``correct``; a hit anywhere else, or on a
  sample marked ``expect_miss``, is a ``false_positive`` — located, and not a
  recovery;
* a sample with neither ``expected_box`` nor ``expect_miss`` is ``unknown``.
  It counts in the hit rate and in no rate that claims correctness;
* a strategy that raises is ``error``, including on a sample that expects a
  miss;
* a strategy that modifies the frame is refused with
  ``HealingEvaluationError``: the next version would be measured on a
  different image.

Coordinates are screen coordinates. ``origin`` is the screen position of the
frame's top-left pixel (negative on a monitor left of or above the primary)
and ``scale`` is frame pixels per screen unit.

A dataset can also be a JSON file with frame images beside it, which is what
the executor command, the MCP tool and the GUI evaluate::

    {"schema_version": 1,
     "samples": [{"id": "submit", "frame": "frames/submit.png",
                  "template": "submit.png",
                  "expected_box": [100, 60, 156, 92],
                  "origin": [0, 0], "scale": 1.0, "region": null}],
     "versions": {"v1": {"strategy": "template", "threshold": 0.9},
                  "v2": {"strategy": "template", "threshold": 0.9,
                         "scales": [1.0, 1.5]}},
     "thresholds": {"v2": {"min_correct": 1, "max_false_positive": 0}}}

    from je_auto_control import evaluate_healing_dataset
    payload = evaluate_healing_dataset("dataset.json")
    payload["passed"], payload["violations"]

Image paths are relative to the dataset file and may not leave its directory.

A version can also name the ``vlm`` strategy, which shows a ``utils/vision``
backend the sample's own frame (the region crop, as PNG — never a new
screenshot) and asks for the sample's ``description``::

    "samples": [{"id": "submit", "frame": "frames/submit.png",
                 "description": "the green Submit button",
                 "expected_box": [100, 60, 156, 92]}],
    "versions": {"v1": {"strategy": "template", "threshold": 0.9},
                 "v3": {"strategy": "vlm", "backend": "anthropic",
                        "model": "…",
                        "price": {"input_per_mtok": 5.0,
                                  "output_per_mtok": 25.0}}},
    "thresholds": {"v3": {"max_model_calls": 50, "max_cost": 0.25}}

``backend`` is ``anthropic``, ``openai`` or ``null``; left out, it is the
backend ``AUTOCONTROL_VLM_BACKEND`` and the API keys select. ``null`` makes no
request and turns every sample into an ``error``, which is what a machine with
no key should measure. From Python, ``evaluate_healing_dataset(path,
backends={"fake": my_backend})`` lets a version name a backend object of your
own, and ``vlm_strategy(backend, model=..., price=...)`` is the callable for
``evaluate_locators``. **A ``vlm`` version against a real backend sends every
frame to that service and is billed by it.**

Every report and every result row gains ``model_calls``, ``input_tokens``,
``output_tokens`` and ``cost``. Calls are counted by the evaluation (a request
that failed was still made; a sample with no description, or an unavailable
backend, makes none). Tokens come from the backend's ``last_usage`` — the
Anthropic and OpenAI backends fill it from the response — and ``cost`` is the
backend's own figure or tokens × ``price``. Where nothing was reported the
value is ``None``, never ``0`` and never an estimate; a template version
reports ``model_calls: 0`` and ``None`` for the rest. When any version is
``vlm`` the frames are loaded in colour (the template strategy converts them
to gray itself), so every version is still given the same frame.

The Self-Healing tab shows the result as a comparison table — one version per
row, the baseline first; located, accuracy, false positives and recovery each
as ``count/total (rate)``, then p50 / p95, model calls, tokens in / out and
cost, with ``-`` where nothing was reported — and keeps the full JSON report
(failing samples, threshold violations) beneath it. The same rows are
available headlessly as ``comparison_rows(payload)`` (columns:
``COMPARISON_COLUMNS``).

``benchmarks/self_healing/run.py`` is the fixed regression set: ten frames
drawn in memory (plain, 125% / 150% scale, negative-origin monitor, a region
that must pick the second of two identical targets, a redesigned control, an
absent target, a look-alike neighbour, one unlabelled frame) and three
versions. It captures no screen::

    python benchmarks/self_healing/run.py --check --json report.json

Candidate template revisions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A healed point is never written over a template. A new image is a candidate
that has to be previewed before it replaces anything::

    from je_auto_control import (
        propose_template_revision, preview_template_revision,
        accept_template_revision, revert_template_revision,
    )

    revision = propose_template_revision("submit.png", "submit_new.png")
    preview = preview_template_revision(revision.revision_id,
                                        dataset_path="dataset.json")
    preview["revision"]["validated"]
    accept_template_revision(revision.revision_id)   # backup kept
    revert_template_revision(revision.revision_id)   # backup restored

``propose`` and ``preview`` never touch the template. With a dataset (or
``samples=``), preview runs the current and the candidate template over the
same frames; the candidate is ``validated`` only when it is correct at least
once, at least as often as the current template, and raises no false positive
or error. ``accept`` refuses an unvalidated candidate unless
``allow_unvalidated=True``, and both ``accept`` and ``revert`` refuse when the
template file changed underneath the revision. Revisions live under
``~/.je_auto_control/template_revisions``.

Executor: ``AC_self_heal_evaluate``, ``AC_self_heal_revision_propose /
_preview / _accept / _revert / _list``. MCP: ``ac_self_heal_evaluate``,
``ac_self_heal_revision_*``. GUI: **Self-Healing** tab → Actions menu
(*Evaluate dataset*, *Propose / Preview / Accept / Revert revision*).


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

``summarise_llm_costs()`` with no argument summarises the calls recorded in
``default_cost_store``. The pricing table carries Anthropic's current list
prices for Claude (Fable 5.x, Opus 5.x / 4.x, Sonnet 5 / 4.x, Haiku 4.5 and
older lines; a dated or ``anthropic.``-prefixed id is looked up by its base id)
and OpenAI; override per-call.
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

Credentials in the error text, log tail and metadata are masked before
any backend sees the report, and a backend that raises becomes a failed
``TicketResult`` without stopping the others.

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

Pass ``stop_event=`` (a ``threading.Event``) to stop a run from another
thread: running nodes finish, and every node not yet started is ``skipped``
with the error ``"stopped"``. Executor: ``AC_run_dag``. GUI: **DAG Runner**
tab, whose Actions menu has **Stop DAG**.


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
single call drives Anthropic's computer-use tool (``computer_20251124`` on
``claude-opus-5`` by default, sent under its ``computer-use-2025-11-24`` beta;
``tool_type=`` picks another version and ``beta=`` names its beta). With
``model="claude-opus-5-5"``, which accepts nothing else, the backend sends the
GA ``computer_toolset_20260801`` instead: no beta, several actions per turn,
and screenshots scaled into the model's image limits (2576 px on the long
edge and 4784 visual tokens, so a 1080p screen goes unscaled) with the
model's coordinates mapped back to the screen. ``zoom`` is answered with a
full-resolution crop of the region it names::

    from je_auto_control import run_computer_use
    result = run_computer_use(
        "open Calculator, compute 12 * 7, screenshot the result",
        max_steps=15, wall_seconds=120.0,
    )

Auto-detects display size. Screenshots are fitted into the model's image tier
(Claude 4.7 and later: 2576 px / 4784 visual tokens; older models: 1568 px /
1568 tokens) on the beta tool as well, which declares that fitted size as its
display and maps the model's coordinates back to the screen. Takes ``max_steps`` + ``wall_seconds``
budgets so a runaway loop can't drain the API; setting ``stop_event=`` (a
``threading.Event``) ends the run before its next step, with
``final_message`` ``"stopped"``. Executor: ``AC_computer_use``. GUI:
**Computer Use** tab, whose Actions menu has **Stop**. Closing the window
asks a running job to stop and waits up to 10 seconds for it.

The Anthropic backends (this one and ``AnthropicAgentBackend`` behind
``AC_run_agent``) never edit a turn they have already sent. When the
conversation would hold more than three screenshots (or more than 20 MB of
them), the next request starts a new history instead: one message with the
goal, the list of actions executed so far with their outcomes, and the current
screenshot. Earlier turns and their thinking blocks are not replayed, so the
model continues from that summary alone. The OpenAI backend still replaces
older screenshots with a text note in place.


WebRunner executor + MCP integration
------------------------------------

Brand-new convenience commands on top of the existing
``je_web_runner`` bridge::

    je_auto_control.web_open("https://example.com")
    je_auto_control.web_screenshot("loaded.png")
    je_auto_control.web_quit()

Executor: ``AC_web_open / _quit / _screenshot / _current_url``
(joining the existing ``AC_web_run``). MCP exposes the same surface
as ``ac_web_*``. GUI: **WebRunner** tab; Script Builder: the
**Browser** category.

``["AC_web_run", {"action": "WR_to_url", "params": {"url": "..."}}]``
runs one ``WR_*`` command through WebRunner's ``execute_one`` (its
command gates, retry policy and failure screenshots) when the
installed WebRunner has it. A failing command raises
``WebRunnerBridgeError``, so the executor records it and the script
goes on, as with any other failed action.


Chat-ops bot
------------

Transport-agnostic ``CommandRouter`` plus a polling Slack adapter so
``/run <script>`` over Slack hits the same execution path as the
scheduler. Built-in commands: ``/help``, ``/scripts``, ``/run``,
``/screenshot [name]``, ``/status``. ``/screenshot`` writes into the
context's ``screenshot_dir`` (default: ``je_auto_control_chatops`` in the
temp directory) and keeps only the file name it is given. The Slack
adapter goes through the package HTTP client, so the egress policy applies.
RBAC via the ``required_role``
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
* ``backend`` — ``"anthropic"`` or ``"openai"``. ``AC_run_agent`` uses a focused, low-risk
  computer-use allow-list by default instead of exposing the complete ``AC_*`` catalogue.
  Applications that need a custom set should construct the backend with
  ``export_anthropic_tools(only=[...])`` or ``export_openai_tools(only=[...])``.
* ``max_steps`` (default 25) and ``wall_seconds`` (default 300.0).
* ``model`` / ``max_tokens`` — backend-specific overrides.

Each model request times out after 120 s, and only the three newest
screenshots are resent (older ones become a text note), so a long run stays
under the API's request size limit. ``export_anthropic_tools(only=[...])``
offers exactly the listed commands — an empty list offers none.

The Anthropic-only Computer-Use raw path (``computer_20251124``) is
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
