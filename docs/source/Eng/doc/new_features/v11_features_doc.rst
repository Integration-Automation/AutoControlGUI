==================================================
New Features (2026-06-19) — Test & Tooling Batch
==================================================

Three quality-of-life tools, all pure standard library and wired through
the full stack (facade, ``AC_*`` executor commands, MCP tools, Script
Builder): seeded synthetic test data, an MCP registry ``server.json``
generator, and risk-based test selection.

.. contents::
   :local:
   :depth: 2


Synthetic test data
===================

Generate deterministic fake rows from a tiny field schema — to drive
data-driven runs without shipping real PII. No Faker dependency; the same
``seed`` always yields the same rows::

    from je_auto_control import generate_rows, write_dataset

    rows = generate_rows({
        "name": "name",
        "email": {"type": "email", "domain": "acme.test"},
        "age": {"type": "int", "min": 18, "max": 65},
        "status": {"type": "choice", "choices": ["new", "vip"]},
    }, count=100, seed=7)

    write_dataset(rows, "people.csv")   # or .json

Supported field types: ``first_name``, ``last_name``, ``name``,
``username``, ``email``, ``phone``, ``city``, ``company``, ``word``,
``sentence``, ``uuid``, ``bool``, ``int`` (min/max), ``float``
(min/max/ndigits), ``choice`` (choices), ``date`` (start/end).

The ``AC_generate_data`` command writes a file (then feed it to
``AC_load_data``) or returns the rows inline.


MCP registry manifest
====================

Publish a ``server.json`` describing this AutoControl MCP server so
MCP-aware agents and IDEs can discover and install it. The manifest is
built from live package metadata, so it never drifts::

    from je_auto_control import write_server_manifest

    write_server_manifest("server.json", include_tools=True)

``include_tools`` embeds the live tool list under ``_meta`` (without
touching the registry-valid core fields). Also exposed as
``AC_mcp_manifest`` and the ``ac_mcp_manifest`` MCP tool.


Risk-based test selection
========================

Instead of always running the whole suite, rank flows by how *risky* they
are — recently failing, flaky, stale, or never-run — using the run-history
store, then run the riskiest first (or only the top-k)::

    from je_auto_control import select_flows, rank_flows

    ranked = rank_flows(["login", "checkout", "report"])
    risky = select_flows(["login", "checkout", "report"], k=2)

The score is ``0.5*failure_rate + 0.2*last_failed + 0.2*flakiness +
0.1*staleness``; a never-run flow scores ``0.8`` (untested is risky).
Exposed as ``AC_rank_tests`` / ``AC_select_tests`` and the
``ac_rank_tests`` / ``ac_select_tests`` MCP tools.
