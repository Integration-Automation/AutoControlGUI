================================================
New Features (2026-06-18) — CLI & Integrations
================================================

Eight headless capabilities that round out scripting, integration, and
continuous-integration use: a real command-line interface,
recording-to-code generation, and first-class HTTP / SQL / email / PDF /
wait steps. Every feature ships a headless Python API, an ``AC_*``
executor command, an MCP tool, and a visual Script Builder entry, and is
covered by headless tests — the network, SMTP, and PDF backends are
injected, so nothing touches the outside world.

.. contents::
   :local:
   :depth: 2


Command-line interface
======================

The package now installs a ``je_auto_control`` console script for running
and inspecting action files from a shell or CI pipeline::

    je_auto_control run script.json --var user=alice --dry-run
    je_auto_control validate script.json      # alias: lint
    je_auto_control list-commands --filter mouse --json
    je_auto_control fmt script.json --check
    je_auto_control record out.json --duration 5
    je_auto_control codegen script.json --target pytest -o test_flow.py
    je_auto_control version

``run`` executes (``--dry-run`` validates and lists steps without acting),
``validate`` / ``lint`` checks structure and rejects unknown commands,
``fmt`` canonicalises the JSON, ``record`` captures input, ``codegen``
emits source (below), and ``list-commands`` prints the live executor
catalogue.


Code generation
===============

Turn a recording or an action file into committable, runnable source::

    from je_auto_control import generate_code, generate_code_file

    code = generate_code(actions, target="pytest", style="calls")
    generate_code_file("flow.json", "test_flow.py", target="pytest")

``target`` is ``pytest`` / ``python`` / ``robot``. The default ``calls``
style maps each ``AC_*`` command to its facade call
(``ac.click_mouse(...)``) and falls back to the executor for flow control,
private adapters and any action holding a ``${...}`` placeholder (only the
executor resolves them); the ``actions`` style embeds the list and replays it
through the executor. Every replay is
``ac.executor.execute_action(..., raise_on_error=True)``, so a generated test
fails at the first failed action. An action list the executor would refuse
(``[1]``, an action with a third element) is refused here too.

Executor command: ``AC_generate_code``. CLI: ``je_auto_control codegen``.


Action journal and candidate scripts
====================================

The action journal is an opt-in, append-only JSON-lines record of every action
the executor runs -- whichever entry point started it (Python, CLI, GUI, REST,
socket, MCP)::

    from je_auto_control import (
        start_action_journal, stop_action_journal, read_events,
        generate_candidate_from_log,
    )

    run_id = start_action_journal("journal.jsonl")["run_id"]
    execute_action(actions)
    stop_action_journal()

    for event in read_events("journal.jsonl", run_id=run_id):
        print(event.sequence, event.command, event.status, event.parent_id)

With no journal started, dispatch pays one global read per action and allocates
nothing. Each event (``ActionEvent``, ``schema_version`` 1) carries:

* ``run_id`` / ``step_id`` / ``parent_id`` / ``sequence`` -- a step nested in a
  block names the block as its parent; an ``AC_parallel`` branch keeps the
  block as parent and its ``branch`` index, and ``sequence`` is the order the
  steps started in (also the order of the lines in the file);
* ``command`` and ``params`` -- the arguments *as written*: ``${var}`` and
  ``${secrets.NAME}`` references stay references. Secrets are masked **before**
  the line is written (the same rules as the executor's log, plus tuples), and
  a value JSON cannot hold is replaced by ``{"$unserialisable": "<type>"}``;
* ``unreplayable`` -- for each such path (``params.password``,
  ``params.body[0][1].token``) the reason it cannot be replayed;
* ``status`` -- ``ok``, ``error`` or ``incomplete``. A step is written when it
  starts and again when it ends, so a step whose end never reached the file
  (the process died, ``Ctrl+C``) reads back as ``incomplete``, never as a
  success;
* ``outcome`` -- the returned value by type and size only (numbers and booleans
  by value); returned text is never stored, and an outcome is never an input;
* ``artifacts`` (optional) -- what the step left behind, each
  ``{"kind": ..., "path": ...}`` or ``{"kind": "trace", "id": ...}``: a file
  named by a path argument or result key (``file_path``, ``output_path``,
  ``path``...) that was written while the step ran, a report written by
  ``generate_html_report`` / ``_json_`` / ``_xml_``, a ``trace_id`` /
  ``traceparent`` in the result, and anything a command attaches itself with
  ``note_artifact(kind, path=..., ident=...)``. The error screenshot a
  scheduler, trigger or hotkey takes after a failed run is attached to the
  step that ended last on that thread. The schema is still version 1: a step
  with no artifacts writes the line it always did, and older lines read back
  with ``artifacts == ()``.

Everything recorded between start and stop belongs to one ``run_id`` (pass
``run_id=`` to choose it). If the journal file cannot be written, journalling
stops and the automation continues; ``action_journal_status()`` reports the
error. Steps a runner hands to a thread pool other than ``AC_parallel`` (the
DAG runner, a device matrix) are recorded without a parent.

A run-history row started while a journal is on records that journal's file
and run id (``RunRecord.journal_path`` / ``journal_run_id``; pass them to
``HistoryStore.start_run`` or call ``link_journal`` to set them yourself).
``AC_history_list``, ``ac_list_run_history``, the REST history route and the
Run History tab's detail show both. An existing ``run_history.sqlite`` gains
the two columns the first time it is opened; clearing history never deletes a
journal file.

``generate_candidate_from_log(path, run_id=..., target="pytest",
style="actions")`` turns one run into a ``CandidateScript`` -- ``code``,
``actions``, ``manifest``, ``warnings`` and ``observed_path_only``:

* a top-level step is emitted as it was written, so a recorded ``AC_loop`` /
  ``AC_if_*`` / ``AC_parallel`` keeps its control flow;
* where a block cannot be rebuilt (the journal started inside it, its
  arguments could not be stored, it calls a macro the run did not define) the
  steps that actually ran beneath it are emitted instead, marked ``observed``
  in the manifest, and ``observed_path_only`` is true -- the candidate replays
  the path that run took, and no branch that did not run is invented. Inside
  an observed ``AC_retry`` only the last attempt is kept (the manifest counts
  the attempts);
* a masked secret becomes a ``${journal_redacted_N_M}`` reference, which fails
  as an unknown variable until you replace it;
* failed and unfinished steps are kept (they are the script's input) and
  listed in the warnings;
* the manifest records, per step, the journal line it came from, and the
  checks that were run: the source is parsed, command names are looked up and
  the list goes through the executor's dry run. Nothing read from the log is
  executed or evaluated.

Executor commands: ``AC_journal_start`` / ``AC_journal_stop`` /
``AC_journal_status`` / ``AC_journal_read`` / ``AC_journal_runs`` and
``AC_generate_code_from_journal``. MCP tools: ``ac_journal_start`` /
``ac_journal_stop`` / ``ac_journal_status`` / ``ac_journal_read`` /
``ac_journal_runs`` and ``ac_generate_code_from_log``. CLI::

    je_auto_control codegen --from-log journal.jsonl --run-id RUN \
        --target pytest -o test_flow.py --manifest test_flow.manifest.json

``--run-id`` may be omitted when the journal holds one run; ``--style``
defaults to ``actions`` here (``calls`` for an action file). GUI: Run History
tab → Actions menu (start / stop the journal, save a candidate script);
Recording Editor → *Import journal run…*; Script Builder → *Import journal*.


HTTP / API
==========

A dependency-free HTTP(S) client for hybrid UI + API flows::

    from je_auto_control import http_request

    resp = http_request(
        "https://api.example/items", method="POST",
        json_body={"name": "Sam"},
        headers={"X-Trace": "1"},
        auth={"type": "bearer", "token": "..."},
        timeout=30.0)
    assert resp["status"] == 201

Returns ``{status, ok, headers, set_cookie, text, json, url}``; non-2xx
responses are returned rather than raised, so you can assert on the status
code. A repeated header is joined with ", " in ``headers``; ``set_cookie``
lists every ``Set-Cookie`` value. A body over 64 MiB raises ``URLError``. Only
``http`` / ``https`` schemes are allowed. ``AC_http_to_var`` now shares
the same client, so it can POST bodies and send headers / auth.

Executor command: ``AC_http_request``.


SQL
===

Read-only, parameter-bound SQLite queries::

    from je_auto_control import query_sqlite

    rows = query_sqlite("app.db", "SELECT id, name FROM users")
    count = query_sqlite("app.db",
                         "SELECT COUNT(*) FROM users WHERE active = ?",
                         params=[1], fetch="scalar")

Queries are restricted to a single read-only ``SELECT`` / ``WITH``
statement, run over a read-only connection, with values always bound as
parameters (never string-interpolated).

Executor commands: ``AC_sql_to_var`` (rows / one row / scalar into a
variable) and ``AC_assert_db`` (a scalar query asserted with
eq / ne / lt / gt / contains / ...).


Email (SMTP)
============

Send mail — for example a flow's report — over the standard library::

    from je_auto_control import send_email

    send_email(
        {"sender": "bot@x.com", "to": ["qa@x.com"],
         "subject": "Run passed", "body": "All green",
         "attachments": ["report.html"]},
        {"host": "smtp.x.com", "port": 587,
         "username": "bot@x.com", "password": "..."})

TLS is enabled by default (STARTTLS, or implicit SSL when ``use_ssl`` is
set; the port then defaults to 465 instead of 587) over a verified default context; supports multiple recipients, CC,
HTML bodies, and file attachments.

Executor command: ``AC_send_email``.


PDF
===

Extract text from and assert on PDF documents (optional ``pypdf``
backend — ``pip install je_auto_control[pdf]``)::

    from je_auto_control import extract_pdf_text, assert_pdf_text

    text = extract_pdf_text("invoice.pdf", pages=1)
    assert_pdf_text("invoice.pdf", "Total: $50.00")

Executor commands: ``AC_pdf_to_var`` (text into a variable) and
``AC_assert_pdf_text`` (text present / absent, optionally on a page).


Smart waits
===========

Two waits that replace unreliable ``sleep`` calls::

    from je_auto_control import (
        wait_until_file, wait_until_port, wait_until_process)

    wait_until_file("~/Downloads/report.pdf", stable_for_s=1.0)
    wait_until_port("127.0.0.1", 8080, timeout_s=30.0)
    wait_until_process("myserver", present=True, timeout_s=30.0)

``wait_until_file`` returns once a file exists, is at least ``min_size``
bytes, and its size has held steady for ``stable_for_s`` (a download has
finished). ``wait_until_port`` returns once a TCP connection to
``host:port`` succeeds — the companion to launching a server. ``wait_until_process``
returns once a process whose name contains the target appears (or, with
``present=False``, exits) — the companion to ``launch_process`` /
``kill_process`` (requires psutil). All return a ``WaitOutcome`` and honour
a hard ``timeout_s`` cap.

Executor commands: ``AC_wait_for_file``, ``AC_wait_for_port``,
``AC_wait_for_process``.


Security
========

HTTP and SMTP enforce ``http`` / ``https`` or TLS with verified
certificates and explicit timeouts; SQL is read-only and parameter-bound;
all user-supplied file paths are resolved with ``realpath`` before I/O.
