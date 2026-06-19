==================================================
New Features (2026-06-19) — SBOM & Suite Sharding
==================================================

Two pure-standard-library ops tools from the security and scale research
angles, wired through the full stack (facade, ``AC_*`` executor commands,
MCP tools, Script Builder): a **CycloneDX SBOM generator** and a
**duration-aware suite sharder** (with shard-result merge).

.. contents::
   :local:
   :depth: 2


CycloneDX SBOM
=============

Supply-chain regulation (EU Cyber Resilience Act, US EO 14028) increasingly
requires a machine-readable Software Bill of Materials. ``build_sbom`` walks
the installed Python distributions and emits a **CycloneDX 1.6** JSON
document — no third-party dependency::

    from je_auto_control import build_sbom, write_sbom

    sbom = build_sbom("je_auto_control")        # dependency closure of the pkg
    sbom = build_sbom(None)                      # every installed distribution
    write_sbom("sbom.cdx.json", "je_auto_control",
               extra_components=[{"type": "file", "name": "login.json",
                                  "version": "1"}])

Each component carries ``name`` / ``version`` / ``purl`` (``pkg:pypi/...``)
and, when available, its license. ``extra_components`` lets you inventory
action files alongside code. Exposed as ``AC_generate_sbom`` /
``ac_generate_sbom``.


Duration-aware suite sharding
============================

Splitting a suite across N workers by *count* wastes time when tests differ
in duration — the slowest worker defines wall-clock. ``shard_flows`` balances
shards by **historical per-flow duration** from the run-history store using
greedy bin-packing::

    from je_auto_control import shard_flows, merge_results

    shards = shard_flows(all_flows, shards=4)    # ~equal time per shard
    # ... each worker runs its shard, produces a report ...
    report = merge_results([shard_report_1, shard_report_2, ...])

Flows with no history fall back to the mean of known flows (so new tests
spread evenly). ``merge_results`` recombines per-shard report dicts — summing
``total`` / ``passed`` / ``failed`` / ``skipped`` / ``errors`` and
concatenating ``results``. Exposed as ``AC_shard_suite`` / ``AC_merge_results``
(and ``ac_shard_suite`` / ``ac_merge_results``).
