==================================================
New Features (2026-06-19) — Heal Analytics & Secret Scan
==================================================

Two pure-standard-library audit/analysis tools: aggregate the self-healing
log into drift metrics, and scan action JSON for hardcoded secrets. Full
stack.

.. contents::
   :local:
   :depth: 2


Self-heal analytics
==================

::

    from je_auto_control import analyze_heal_log, heal_stats

    analyze_heal_log(limit=200)     # over the live self-heal log
    heal_stats(events)               # over a supplied event list

Aggregates self-heal events into ``{total, healed, heal_rate, by_method,
fallbacks, fallback_rate, avg_duration_ms, top_brittle}`` — surfacing
locators that increasingly need the VLM fallback (decaying selectors) before
they fail. Exposed as ``AC_heal_stats`` / ``ac_heal_stats``.


Secret scan
==========

::

    from je_auto_control import scan_secrets

    scan_secrets(action_json)   # [{path, kind, preview}, ...]

Walks a JSON-like structure and flags string values that look like secrets —
by key name (``password`` / ``token`` / ``api_key`` …), by value pattern
(AWS / GitHub tokens, private-key blocks), or by high Shannon entropy — that
should reference the vault (``${secrets.NAME}``). Values already referencing
the vault are ignored; previews are masked. Exposed as ``AC_scan_secrets`` /
``ac_scan_secrets``.
