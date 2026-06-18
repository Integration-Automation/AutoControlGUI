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
(``ac.click_mouse(...)``) and falls back to ``ac.execute_action([...])``
for flow control and private adapters; the ``actions`` style embeds the
list and replays it through the executor.

Executor command: ``AC_generate_code``. CLI: ``je_auto_control codegen``.


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

Returns ``{status, ok, headers, text, json, url}``; non-2xx responses are
returned rather than raised, so you can assert on the status code. Only
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
set) over a verified default context; supports multiple recipients, CC,
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

    from je_auto_control import wait_until_file, wait_until_port

    wait_until_file("~/Downloads/report.pdf", stable_for_s=1.0)
    wait_until_port("127.0.0.1", 8080, timeout_s=30.0)

``wait_until_file`` returns once a file exists, is at least ``min_size``
bytes, and its size has held steady for ``stable_for_s`` (a download has
finished). ``wait_until_port`` returns once a TCP connection to
``host:port`` succeeds — the companion to launching a server. Both return
a ``WaitOutcome`` and honour a hard ``timeout_s`` cap.

Executor commands: ``AC_wait_for_file``, ``AC_wait_for_port``.


Security
========

HTTP and SMTP enforce ``http`` / ``https`` or TLS with verified
certificates and explicit timeouts; SQL is read-only and parameter-bound;
all user-supplied file paths are resolved with ``realpath`` before I/O.
