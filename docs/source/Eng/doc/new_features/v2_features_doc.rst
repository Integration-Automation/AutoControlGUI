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
point targeting ``je_auto_control_pytest``. Automatic loading imports only
pytest; the automation facade loads when a fixture or failure screenshot needs it.
Reinstall editable checkouts after upgrading to refresh entry-point metadata.
Explicit ``je_auto_control.utils.pytest_plugin`` loading remains supported. Fixtures
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
  with tool-use messages; each screenshot is fitted into the model's image
  tier and the ``x`` / ``y`` of a tool call mapped back to the screen) or ``"openai"`` (uses ``export_openai_tools()``
  with Chat Completions function calling).
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


Legacy CLI failure status
-------------------------

``python -m je_auto_control -e/-d/--execute_str`` now returns exit code 1
for failed actions, matching ``je_auto_control run``. Successful runs return 0.
Directory runs accumulate failures across files; stderr reports the failure count.


Execution variable scopes
-------------------------

Each public action run starts fresh. Nested calls share its scope; parallel
branches and DAG workers deep-copy variables. REST/MCP requests are independent.
An explicitly owned ``Executor`` retains its state outside a public scope.
To share a run across calls and inspect its variables::

    import je_auto_control as ac
    with ac.execution_scope({"seed": "hello"}) as scope:
        ac.execute_action([["AC_set_var", {"name": "result", "value": "${seed}"}]])
        assert scope["result"] == "hello"

Opaque variable values used in parallel work must support deep copying.
Use ``isolated=True`` to start an independent nested scope; exit restores the parent.


USB request correlation
-----------------------

JSON operations carry an optional ``request_id`` string (up to 64 characters).
Current clients generate IDs; current hosts echo them in OPEN/RESUME, LIST,
transfer, CLOSE, ERROR and CREDIT responses, after fragment reassembly.
Late replies cannot complete another request. Credits must match the request
and claim and are applied once; late OPEN claims are released.
The binary header is unchanged, and old peers still work.

After a reply timeout against a legacy or unconfirmed host, the client closes
and cancels its pending operations; handles report ``closed``. Reconnect the
transport and create a new ``UsbPassthroughClient`` before retrying.
A confirmed correlated peer can continue after timeout with a fresh request ID.

Public-only action signature deployment
---------------------------------------

Signatures authenticate exact bytes with Ed25519, a version-2 JSON envelope,
a trusted public-key fingerprint and a domain prefix. Keys are raw 32-byte or
PEM Ed25519 material. Generation preserves existing keys and rejects mismatched
pairs. Private files are created with mode 0600; use host ACLs on Windows.

On the offline signing host::

    je_auto_control signing-keygen --private-key private.pem --public-key public.pem
    je_auto_control sign flow.json --private-key private.pem

Deploy only flow.json, flow.json.sig and public.pem to the execution host.
Set JE_AUTOCONTROL_SIGNING_PUBLIC_KEY to its absolute public.pem path and
JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS=1. Do not configure
JE_AUTOCONTROL_SIGNING_PRIVATE_KEY there. Verification never creates keys::

    je_auto_control verify flow.json --public-key public.pem
    je_auto_control run flow.json

The Python API mirrors the CLI::

    from pathlib import Path
    import je_auto_control as ac
    ac.create_signing_keypair(Path('private.pem'), Path('public.pem'))
    ac.sign_action_file('flow.json', private_key_path='private.pem')
    assert ac.verify_action_file('flow.json', public_key_path='public.pem').verified

Script Builder offers AC_create_signing_keypair, AC_sign_action_file and
AC_verify_action_file. MCP offers the same names with the ac_ prefix; generation
and signing mutate files and are excluded from read-only mode.

Legacy plain-hex HMAC and version-1 envelopes are rejected by default. To migrate,
verify an old file explicitly, then re-sign it on the offline signing host::

    je_auto_control verify old.json --allow-legacy-hmac --legacy-key-file old.key
    je_auto_control sign old.json --private-key private.pem

Python verification requires allow_legacy_hmac=True and explicit legacy key
material. Enforced loaders require JE_AUTOCONTROL_ALLOW_LEGACY_HMAC=1 and
JE_AUTOCONTROL_LEGACY_SIGNING_KEY pointing to an existing key file. Remove both
after migration. Signing in legacy mode requires legacy_hmac=True and an explicit
key. There is no automatic personal signing key or private-key fallback.

Signed-file enforcement checks file loaders, not inline action lists. It does
not isolate scripts or prevent an authorized operator from modifying the host.
Keep the private key off execution hosts; role authorization is a separate gate.

MCP filesystem and reference boundaries
---------------------------------------

JE_AUTOCONTROL_MCP_ROOTS is an OS-path-separator list of allowed roots.
Client roots/list narrows deployment roots by intersection, never widens them.
Multiple roots and HTTP peers are isolated; filesystem resources use the same
effective roots. An explicitly empty list denies filesystem arguments. With
no configured or client roots, file access remains compatible. Read-only mode
is a separate setting and is not enabled automatically.

Schemas mark actual file arguments with format=path and their read/write
operation. Nested attachments, DAG action files, locator templates and output
paths are checked too. Conditional image targets are checked only in image
mode; text targets, JSONPath, SBOM distribution names and URLs retain their
meaning. Relative file paths resolve against the first effective root; symlink
escapes are rejected by realpath checks, including nonexistent write targets.

MCP env:// references default to deny; set the comma-separated exact-name
JE_AUTOCONTROL_MCP_ALLOWED_ENV allowlist. Recursive env:// and file:// references
use the same per-call policy. secret:// is still refused in recorded surfaces.
For a local headless call with explicit limits::

    from pathlib import Path
    import je_auto_control as ac
    policy = ac.PathPolicy(roots=[Path('workspace')], allowed_env=['BUILD_ID'])
    value = ac.resolve_ref('file://settings.txt', policy=policy)

Local Python resolvers without a policy preserve existing behavior. A remote
call always retains its policy even through the executor's reference adapters.
These checks constrain declared file arguments and value references; arbitrary
script/process tools and trusted default stores still require authorized users.
They are not an operating-system sandbox against local filesystem races.
Plugins must mark filesystem fields using the same schema metadata.

Viewer download migration
-------------------------

TCP and WebSocket viewers now use ~/Downloads/AutoControl, or the locally set
JE_AUTOCONTROL_DOWNLOAD_DIR. Hosts send relative destination names::

    host.send_file_to_viewers('local.bin', 'reports/from_host.bin')

Absolute paths, drive-relative paths, UNC paths, parent traversal, NULs, alternate
streams and symlink escapes are rejected before opening a part file. Transfer
completion re-checks the boundary before replacing the destination. Existing
partial-transfer integrity checks remain in force. Host FileReceiver() behavior
is preserved. A local client can choose a different bounded receiver::

    from pathlib import Path
    from je_auto_control import FileReceiver
    viewer.set_file_receiver(FileReceiver(base_dir=Path('downloads')))

GUI viewers use the same default boundary. WebRTC retains its existing bounded
inbox and file-name protocol. Absolute host-to-viewer examples must migrate to
relative names; a deliberately unbounded custom receiver remains a local choice.

Registry publishing identity
-----------------------------

The default server manifest name is io.github.integration-automation/autocontrol.
Its repository is https://github.com/Integration-Automation/AutoControlGUI.
The stable PyPI package remains je_auto_control; dev.toml retains je_auto_control_dev.
Regenerate server.json before publishing to use the approved namespace.
Existing custom name/repository_url overrides remain supported.

Remote execution boundaries
---------------------------

Remote execution uses an explicit server-owned capability catalog. Unknown
commands require admin regardless of provider ``readOnly`` hints; saving a screenshot
to a file also requires admin access. Nested, loaded and flow-block actions check
declared filesystem paths after interpolation and positional/default binding.
Parallel and deferred work retain the caller's identity and allowed roots;
each remote request and deferred delivery has independent script variables.
Configured signing and encryption keys must also lie within the effective roots,
or use an explicit in-memory key. Local calls without a policy retain existing behavior.
Color/HSV and VLM results use the actual clipped capture origin. Windows restore
accepts a minimized window returning to its previous maximized state.

Structured action journals (Beta)
---------------------------------

Use the typed ``je_auto_control.api.journal`` entry point to record actions and
read selected runs. The same three operations are available through the facade,
``AC_execute_journaled``, ``AC_read_action_journal``, ``AC_list_journal_runs``, MCP
and Script Builder. Run History offers recording and read-only preview in Actions.

.. code-block:: python

    from je_auto_control.api.journal import execute_journaled, read_action_journal
    run = execute_journaled([["AC_sleep", {"seconds": 0}]], "actions.jsonl", run_id="demo")
    events = read_action_journal("actions.jsonl", run_id=run["run_id"])


Schema version 1 stores separate inputs and outcomes, run/step/parent IDs, source
file paths and step indices. Start and terminal records are appended under a
shared run lock; reads retain start order and materialize each step's latest
status. Interrupted steps remain ``incomplete``. Exact ``${secrets.NAME}`` input
references survive; secret literals are masked before logging or append and
marked non-replayable. Unknown payload objects are omitted with reasons, without
calling their repr/str hooks during journal serialization.

For explicit recording around an executor call, use ``with ActionJournal(path).run()``.
Set ``JE_AUTOCONTROL_ACTION_JOURNAL`` to enable automatic executor recording; without
it, existing calls keep their behavior. Reads and previews never execute actions.
Journal paths and their lock files follow the effective filesystem policy.

Fixed-frame self-healing comparison (Beta)
------------------------------------------

Use ``je_auto_control.api.healing`` to compare locator versions on identical saved
frames with labelled boxes, expected misses, origins and pixel/logical scales.
.. code-block:: python

    from je_auto_control.api.healing import compare_healing_versions
    report = compare_healing_versions("benchmarks/self_healing/dataset.json", {
        "before": {"template_path": "benchmarks/self_healing/before.png"},
        "after": {"template_path": "benchmarks/self_healing/after.png"}},
        report_path=".test-tmp/healing-report.json")


JSON and HTML reports retain frame hashes, expected geometry and original run/step
context. Counts include image hits, VLM attempts, misses, errors and unknown labels.
Accuracy, false-positive and recovery rates include numerators/denominators;
p50/p95 use linear interpolation over all attempts. Costs remain unknown when
unavailable. Unlabelled samples never count as correct; wrong VLM guesses never
count as recovery. Historical operation verification is separate from detection
and is not attributed to a newly compared version.

``create_template_candidate``, ``preview_template_candidate``,
``validate_template_candidate``, ``accept_template_candidate`` and
``revert_template_revision`` provide immutable snapshots and explicit review.
Acceptance requires perfect labelled validation with a positive hit and no
errors/false positives, plus an unchanged baseline/candidate hash. Preview never
applies changes; revert checks that the accepted image remains current.

All six operations have matching ``AC_*``, MCP and Script Builder entries.
Self-Healing's Actions menu runs comparisons/revision work in a scoped worker;
the panel shows metric/failure tables, original steps and baseline/candidate
thumbnails. Runtime HealEvent schema 2 retains actual capture identities,
strategy timings, backend/model and journal IDs; legacy schema 1 remains readable.
Unavailable evidence remains unknown. The committed synthetic benchmark is
offline evidence; physical-device and paid-model validation remain separate.

Journal candidate code generation (Beta)
----------------------------------------

Generate a selected-run candidate through ``je_auto_control.api.codegen``:
.. code-block:: python

    from pathlib import Path
    from je_auto_control.api.codegen import generate_candidate_from_log
    candidate = generate_candidate_from_log(Path("benchmarks/journal_codegen/actions.jsonl"), run_id="demo")
    print(candidate.code, candidate.manifest, candidate.warnings)


Generation validates one journal snapshot and preserves its content hash, all
step/parent/source identities, statuses and observed retry occurrences. Only
completed replayable leaf actions are rendered with the existing code generator.
Failed, interrupted and masked steps remain in the manifest and warnings.
Exact ``${secrets.NAME}`` references survive; literal secrets and outcomes are not
turned into replay inputs. No input repr is evaluated and no result is executed.

Candidates are explicitly **observed path only** and serial in start order;
they do not reconstruct original branch/loop/retry/parallel semantics. Validate
installed command names, required Python arguments and executor dry-run; Python
targets also pass AST validation. Robot's Python AST result is not applicable.
Review the candidate before executing or extending it.
.. code-block:: powershell

    python -m je_auto_control.cli codegen --from-log benchmarks/journal_codegen/actions.jsonl --run-id demo -o .test-tmp/test_observed.py


``-o`` saves source plus ``.manifest.json`` and ``.actions.json`` sidecars; output
cannot replace the input journal. Without it, CLI emits source to stdout and
warnings to stderr. Existing target/style/name/failure-bundle flags remain usable;
journal mode defaults to ``actions``, ordinary action-file mode retains ``calls``.
``generate_journal_candidate``, ``AC_generate_journal_candidate`` and
``ac_generate_journal_candidate`` return the same structured JSON artifact.

Recording Editor and Script Builder expose candidate review in Actions. Preview
shows a sanitized diff, source and provenance in a readonly view using a scoped
worker. Import is a separate editing operation; export saves the reviewed
candidate and sidecars. Neither preview nor import runs generated actions.
The synthetic ``benchmarks/journal_codegen`` example is offline contract evidence.

Ordinary ``${var}`` inputs without recorded resolved bindings are omitted with
a warning; they cannot silently reuse a new executor's variables. Validation
also checks block command objects and required fields. Journal recording binds
positional sensitive parameters, masks sensitive variable getter results and
marks unhandled descendant failures as errors. Successfully caught/retried
failures retain successful container/run status.
Interpolated variable names are conservatively private before recording.
Known private scalar values, including numeric PINs, are masked in result/log copies.

Persistent config server (Beta)
-------------------------------

The signaling service keeps config buckets in SQLite across restarts. Set
``--config-store PATH`` or ``AC_CONFIG_STORE_PATH``; otherwise the database path
is resolved on first use under ``~/.je_auto_control/config_sync.sqlite``.
Importing the API or constructing an app creates no database.

``PUT /config/{user_id}`` requires a version-2 envelope with ``schema_version: 2``,
``base_revision``, ``operation_id`` and ``bucket``. The server checks and writes in
one transaction. GET reports the committed ``revision`` and ``cas_supported: true``.
Stale writes return HTTP 409; an identical operation retry returns the original
revision without replacing later data. Reusing its ID with different data is an error.
Accounts, shared-secret authentication and body/user limits remain enforced.
Browser preflight supports PUT. Pending WebRTC rendezvous sessions retain their TTL.

``je_auto_control.api.config_sync`` exports ``ConfigStore``, ``ConfigBucket``,
``ConfigSyncError``, ``ConfigRevisionConflict`` and ``ConfigStoreCapacityError``.
ConfigSyncClient defaults to protected causal synchronization and a durable outbox.
Explicit ``SyncClientOptions(legacy_writes=True)`` also requires the server's
``--allow-legacy-config-writes`` migration option. The config GUI is still pending.

Causal sync and offline retries (Beta)
--------------------------------------

Use ``causal_upsert``/``causal_remove`` with the client's stable ``device_id`` to edit
definitions. ``SyncEntry`` carries version vectors, origin and operation ID;
``merge_entries`` keeps concurrent alternatives rather than selecting by wall clock.
``ConfigBucket.entries()`` excludes unresolved conflicts and tombstones. Explicit
causal edits can resolve a conflict after review. Legacy timestamp helpers remain available.

``ConfigSyncClient.sync()`` refetches and merges after a confirmed HTTP 409, with
bounded CAS retries. Its SQLite ``SyncOutbox`` persists exact envelopes by endpoint
and account; uncertain success retries the original operation ID after restart.
Authentication remains in memory. Pending, conflict and exhausted-retry data is retained.
``retry_pending(cancel=...)`` uses bounded backoff and checks cancellation between sends.
``close()`` releases the database without losing queued data.

The shared ``__sync_devices__`` registry records acknowledgements and retirement.
New deletions get a committed revision only in their CAS envelope; collection
requires every known active device to acknowledge that revision, never elapsed days.
Retired or unresolved registration state blocks incremental sync and push;
``full_resync()`` explicitly fetches a complete protected snapshot before rejoining.
Pending operations require review before full resync. ``retire_device()`` is explicit.
Local ``SyncOutbox`` peer methods preserve retirement across restart.
These are controlled SQLite/HTTP tests; physical multi-machine checks remain pending.
