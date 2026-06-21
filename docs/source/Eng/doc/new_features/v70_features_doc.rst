JSON Contract & Snapshot Matching
=================================

``json_schema`` validates a value against an authored schema and ``jsonpath``
extracts values, but nothing matched two JSON *payloads* with relaxed rules
(type-only, partial, ignore volatile paths) or diffed them path-by-path for
contract / snapshot tests. This adds that layer; it composes with
``json_schema`` (shape) and ``json_patch`` (structured edits).

Pure standard library (``json``); deterministic; imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import match_json, diff_json, snapshot_json

    report = match_json(actual, {"id": 1, "name": "Ada"})
    if not report.ok:
        for m in report.mismatches:
            print(m["path"], m["kind"])     # e.g. "$.name" "changed"

    # Pact-style "like": values may differ, types must match
    match_json(response, template, match_type=True)
    # subset match: extra keys in `actual` are allowed
    match_json(response, template, partial=True)
    # ignore volatile fields
    match_json(response, template, ignore=["$.created_at", "$.id"])

    diff_json(actual, expected)              # [{path, kind, ...}]
    snapshot_json(actual, "golden/checkout.json")  # write-if-absent, else compare

``match_json`` returns a ``MatchReport(ok, mismatches)`` where each mismatch is
``{path, kind}`` with ``kind`` one of ``missing`` (in expected, absent from
actual), ``extra`` (in actual, absent from expected), or ``changed``. Options:
``partial`` drops ``extra`` mismatches (subset match), ``match_type`` accepts a
``changed`` leaf whose types match (Pact ``like``), and ``ignore`` skips listed
paths. ``diff_json`` is the raw path-tagged diff; ``normalize_json`` returns a
canonical copy (sorted keys, ``drop`` keys removed) for stable comparison;
``snapshot_json`` is golden-master testing (writes the file on first run, then
matches against it). ``true`` stays distinct from ``1``.

Executor commands
-----------------

``AC_match_json`` takes ``actual`` / ``expected`` (objects or JSON strings) plus
optional ``partial`` / ``match_type`` and returns ``{ok, mismatches}``.
``AC_diff_json`` returns ``{diffs}``. Both are exposed as MCP tools
(``ac_match_json`` / ``ac_diff_json``) and as Script Builder commands under
**Data**.
