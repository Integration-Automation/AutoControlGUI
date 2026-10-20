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

Cancellation propagates unchanged before fallback, clicking or miss logging.
Audit writes and reads mask secret values already resolved in the active run.
The original locator outcome remains unchanged; reads do not rewrite legacy logs.

Both strategies now reuse one lazy logical capture. ``screen_region`` means
``[left, top, right, bottom]`` for both, clipped to the actual desktop.
An omitted region searches all monitors when a template is supplied; VLM-only
calls retain a primary capture request. Self-capturing backends that return a
whole layout retain their published origin even for that request. Invalid bboxes
fail before capture. A capture failure is reused rather than retried for fallback.

Audit schema 2 adds run/step IDs (reusing an active action journal), locator identity,
decoded-template/configuration version, frame hash, actual origin/size, logical
scale, per-strategy/capture timing, backend and resolved model. Unknown values and
unavailable USD costs stay null. Old records load as schema 1. PNGs stay transient
and are released at scope exit. First-strategy timing includes capture; capture
time is a subset, not an additional summand. The historical result shape and
``duration_ms`` locate-only meaning remain unchanged.

Click records settle after dispatch: ``issued`` confirms input dispatch only,
``error`` records an ordinary failure and preserves the original exception.
``verified`` stays null without explicit post-operation evidence. Cancellation
does not append a completion event. The GUI accepts a region, displays operation
state and selected-record JSON evidence. Runtime controls live in the Runtime log
subview, separate from fixed-frame comparison. Script Builder provides both live
commands and a JSON field that preserves structured regions while editing.


Explicit post-click verification
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The experimental immutable request API defaults to locating. Verification is
opt-in and requires ``operation="click"``. A Python ``VerificationRequest``
accepts exactly one ``verifier`` callback returning bool, or a ``description``
checked by a configured VLM. A VLM check may incur API cost::

    from je_auto_control import SelfHealRequest, VerificationRequest, self_heal_run

    result = self_heal_run(SelfHealRequest(
        template_path="submit.png",
        operation="click",
        verification=VerificationRequest(description="The confirmation is visible"),
    ))
    # result.verified is True, False or None; found alone is not verification.

VLM availability is checked before input. Verification only runs after successful
click dispatch and obtains a fresh logical PNG. Its optional bbox is independent
of the locator bbox; omitted verification regions request the primary display.
The verification model inherits the locator's explicit model unless overridden.
Callbacks execute outside the pre-click frame scope. Backend checks and their
nested visual helpers share only the new frame. Nothing retries a click after
failed verification, an exception or cancellation.

``AC_self_heal_run`` and MCP ``ac_self_heal_run`` accept a nested JSON ``request``::

    [["AC_self_heal_run", {"request": {
        "template_path": "submit.png", "operation": "click",
        "verification": {"description": "The confirmation is visible"}
    }}]]

JSON verification supports description, model and screen_region; arbitrary
Python callbacks/backends are not accepted. Templates honor active path roots,
including changes at progress checkpoints. Explicit false verification raises
``SelfHealVerificationError`` on AC/CLI (CLI exits 1), retaining its result.
MCP returns structured data with ``isError``. The Python request API returns a
false verdict as data. Exceptions and cancellation propagate unchanged.

Audit rows distinguish ``verified``, ``verification_failed`` and
``verification_error`` from ``issued``/unknown. New optional fields include the
verification description, frame hash, backend/model and error; verify timing is
separate from locate-only ``duration_ms``. Callback checks make no image provenance
claim. Old rows remain readable. GUI **Self-Healing** has an optional post-condition
input, with the configured-VLM cost indicated; click must be selected. Script
Builder provides a structured JSON request field for the new command.

Standalone VLM capture also uses logical geometry and Retina normalization in
memory, including clipped/nonzero origins. ``verify_description`` rejects non-bool
backend replies. Framework assertions stop locator recovery before fallback.
These behaviors have controlled tests; native-device and paid-API acceptance
remain deferred.


Original-step source inspection
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A self-healing call inside a captured executor action records optional
``journal_path`` plus its run/step IDs. Direct calls, legacy rows and a run scope
without an action-step binding have no source path. A canonical path containing
known resolved-secret text is omitted. Explicit inspection is read-only::

    from je_auto_control import inspect_heal_source

    snapshots = inspect_heal_source(event.journal_path, event.run_id, event.step_id)

``AC_self_heal_source`` and MCP ``ac_self_heal_source`` take ``path`` (the row's
journal_path), ``run_id``, ``step_id`` and optional ``limit``. CLI action files
can invoke the same command; Script Builder exposes the fields. The read-only
MCP annotation does not grant viewer access to private journal data.

Select a row in **Self-Healing → Runtime log**, then use **Actions → Inspect
original step**. The Original step subview uses the shared background reader;
Run History's reader also accepts an optional step ID. Changing the selected
healing record clears/cancels its prior source view, closing cancels the reader,
and late results cannot replace a newer target. A newly opened target starts
after the older reader stops, retaining its requester context; closing also
discards pending reads. Old rows report unavailable
source instead of inventing a link. Missing files or unmatched IDs return no
snapshots; malformed journals fail validation.

``inspect_journal`` adds optional ``step_id`` filtering. Both run and step
filters precede the 1–10,000 output limit; the whole file still validates.
Current roots apply at entry, around every progress callback and before return.
Cancellation propagates without a partial result. Start/completion snapshots
remain separate and sanitized. No source inspection executes recorded commands.


Reviewed template candidates
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The experimental candidate workflow uses only explicitly supplied files. It never
captures a screen, sends input or invokes a model. Create a new immutable schema-1
JSON bundle containing exact original bytes, candidate bytes encoded in the
target's PNG/JPEG/BMP format, hashes, canonical target and match threshold::

    from pathlib import Path
    from je_auto_control import (
        create_template_candidate, preview_template_candidate,
        verify_template_candidate, accept_template_candidate,
        revert_template_candidate, write_healing_report,
    )

    create_template_candidate("submit.png", Path("candidate.png").read_bytes(),
                              "candidate.json", threshold=0.9)
    reviewed = preview_template_candidate("candidate.json")
    checked = verify_template_candidate("candidate.json", "dataset.json")
    write_healing_report(checked.comparison, "comparison.html")
    if checked.eligible:
        accepted = accept_template_candidate("candidate.json", "dataset.json",
                                             reviewed.state.revision)
        reverted = revert_template_candidate("candidate.json", reviewed.state.revision)

Preview returns two PNG thumbnails bounded to 512 pixels per side and full-size
metadata. Input images are limited to 16 MiB/16 million pixels; bundles to 48 MiB.
Creation refuses an existing bundle and leaves the target untouched. Verification
uses the same schema-1 sample manifest as fixed-frame evaluation (1 MiB manifest,
500 samples, shared 64 MiB asset budget). ``versions`` may be omitted; if present
it is ignored because the bundle supplies both frozen versions. For example::

    {"schema_version": 1, "samples": [
        {"id": "hit", "frame": "frame.png", "expected_box": [20, 16, 37, 29]},
        {"id": "miss", "frame": "absent.png", "expected_miss": true},
        {"id": "unknown", "frame": "unlabelled.png"}
    ]}

Eligibility requires at least one labelled target, one expected miss and all
labelled cases correct. Unknown samples stay unknown and native operation success
remains separate. JPEG candidates are verified after target-format encoding.
Decoding/matching errors, including constant normalized templates, block acceptance.
The bundle's recorded threshold controls validation; activating an image does
not change a script's locator threshold, which should use the matching setting.

Acceptance always reverifies the dataset and requires ``expected_revision`` from
review. This is SHA-256 of the complete bundle bytes, distinct from the runtime
locator-version hash. Under the target lock, the final progress checkpoint is
followed by bundle-revision, current-path and file-content checks, then one atomic
replacement. State is derived from bytes: original/candidate/conflict/missing,
not approval history. A repeated desired result returns ``changed=False``.
Revert restores exact original bytes only while current content still matches
this candidate or original; later edits and missing files cause conflicts.
Cancellation before commit prevents replacement; cancellation after a completed
replacement does not undo it or relabel success. No observer runs after commit.

Python exposes the five functions above. JSON actions and CLI use
``AC_template_candidate_create/preview/verify/accept/revert``; MCP uses the matching
``ac_template_candidate_*`` names. Create takes ``template_path``,
``candidate_path`` (PNG), ``bundle_path`` and optional ``threshold``. Verify/accept
take ``dataset_path``; accept/revert require ``expected_revision``. MCP preview
adds two image blocks; JSON adapters return metadata. All operations require drive
permission and obey current/enclosing roots, including embedded targets and loaded
samples. Script Builder exposes all five commands. **Self-Healing → Template
candidates** provides previews, JSON evidence and Actions-menu operations with
background progress/cancellation in all four interface languages. Run
``python -m examples.template_candidates`` for a synthetic temporary-file example.
Native-device and paid-API acceptance remain deferred.


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
``auto`` default uses CLI only for optional native-backend absence. Portal
refusal/timeout, failed handshake, device pause or revocation stops native
key/button/pointer input without implicit CLI replay. Repeated refused calls
do not reopen consent. ``libei`` requires native input; ``cli`` explicitly
selects the helpers. After resolving permission, explicitly call
``je_auto_control.linux_wayland.libei.reset_default_backend()`` to permit a
fresh request. Interrupted chords attempt every owned release on the same
backend and preserve the original cancellation. The explicit wtype text path
and screen-capture selection are unchanged.


A native Wayland pointer coordinate outside every granted EIS region, after
raw-coordinate and layout-origin mapping, raises ``LibeiUnavailable`` with
``state="failed"`` and disables automatic CLI fallback. A rejected move emits
no motion/frame or subsequent click. Valid coordinates, devices without
regions, later valid requests on the same sender and explicit CLI selection
retain their existing behavior.

Passive capability snapshots use ``BackendContext``, ``CapabilityStatus``,
``CapabilitySnapshot`` and ``probe_capabilities`` from ``je_auto_control.api``
or the package root. Input covers key/pointer events, independently of wtype text.

.. code-block:: python

   from je_auto_control.api import BackendContext, probe_capabilities
   snapshot = probe_capabilities(BackendContext.current())
   print(snapshot.to_dict())

No-argument ``AC_probe_capabilities`` and read-only ``ac_probe_capabilities``
share that contract with Builder and **Diagnostics → Actions → Inspect input
and capture capabilities**. ``python -m examples.capabilities`` is passive.
The probe reads environment/PATH and cached local state without loading optional
native libraries, connecting, polling, capturing or requesting consent.
Prerequisites remain ``unverified``; ``available`` means last local observation,
which can be stale. Other states are ``needs_permission``, ``needs_dependency``,
``unsupported``, ``paused``, ``revoked`` and ``failed``. Actual operations still
enforce authority. Cached libei availability requires completed handshake plus
active keyboard/absolute-pointer/button/scroll families. Partial grants remain
unverified; paused families and removed required devices report paused/revoked.
XWayland is always ``desktop_wide=False``; other scope flags
remain limited by grants/regions and do not verify every monitor.

Contexts detach facts and allow owner-supplied inert observations without granting
authority. AC/MCP accept no supplied observations; default live results omit
environment values, command arguments, executable paths and native error text.
Permission/pause/revocation/failure cannot imply CLI fallback. Only explicit CLI
selection or observed optional native absence describes that alternative.
Input/capture select independently. Rendering/language changes reuse metadata;
native restore/restart, capture-result/context integration and cancelable active
diagnostics remain pending in ``Progress.md``.


The GUI task infrastructure provides ``gui.task_controller.TaskController``:
``submit(work, owner=widget)`` returns a caller-owned ``TaskHandle`` with
typed ``TaskOutcome`` and ``TaskProgress`` observations. Work receives a
Qt-free ``CancellationToken`` with checkpoints, bounded interruptible waits
and progress reporting. Submission captures context; dispatch refreshes
store-backed identity. Work must receive plain data, avoid widget references
and authorize its own operation. Existing
``DeferredAuthorization.scope()`` still requires input privilege, while
``context_scope()`` only refreshes/binds identity for independently authorized work.

Owner/handle/controller destruction requests cooperative stop and drops
late delivery. Each task has a separate ID/token; callbacks run on the GUI
thread. Cancellation does not forcibly interrupt an uncooperative call
or relabel a successful committed return. Errors/progress use the captured
secret scope; terminal errors retain no exception traceback. Failed thread
starts roll back both registries and preserve the original failure.
This is shared infrastructure: Diagnostics and other panels still await
controller/timeout/stop integration, tracked in ``Progress.md``.

Active diagnostics stop immediately when a check raises explicit cancellation
or a hard control signal, including an explicit exception cause chain.
The original object propagates through the core, SDK, CLI and Diagnostics
action; it is not logged or converted into a failed report row, and later
checks do not run. Ordinary probe errors still produce failed rows and
allow remaining checks. A canceled GUI run can be retried explicitly.
Background workers and cooperative stop controls remain pending.

The Diagnostics tab opens in a localized not-run state. Use **Actions → Run
diagnostics** to start active checks, which can capture the screen or require
portal consent. Opening or retranslating the tab does not start checks.
Explicit headless/AC/MCP diagnostics retain their active behavior. Passive
capability inspection uses its separate action described below.


Abandoned screenshot requests attempt ``org.freedesktop.portal.Request.Close``
on their originating bus with a separate 0.25-second I/O budget. Returned
alternate handles are followed; uncertain replies use the predicted handle.
Completed responses are not closed twice. Original controls survive wrappers
and cleanup. D-Bus writes and reply waits share one budget; interrupted bus
connect/authentication/Hello releases its descriptor even before ``__enter__``
returns. Native compositor/dialog, restore and restart acceptance remain open.


The repository's dev/main headless jobs retain merged test output and runtime
versions even after a native failure. Linux runs under GDB for all-thread
native backtraces; other platforms retain Python faulthandler output. The
``native-<os>-<python>`` artifacts expire after seven days. Failed child exits
still fail CI. Linux first checks the runner outside the suite's debugger;
literal argv and handled SIGINT are preserved. See
:doc:`/getting_started/run_in_ci` for reproduction. Collecting
evidence does not mark pending portal/native lifecycle acceptance complete.


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
