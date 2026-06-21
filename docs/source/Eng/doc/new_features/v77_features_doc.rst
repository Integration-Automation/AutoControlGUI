Data Profiling & Schema Inference
=================================

``data_quality.validate_rows`` *consumes* a hand-written schema and
``stats.describe`` summarises one numeric list — nothing surveyed a whole
row-set to report per-column null fraction, cardinality, inferred type, value
ranges, and top values, nor proposed a starting schema. This adds the profiler
step that feeds the existing validator.

Pure standard library (``collections`` + reuse of ``stats``); imports no
``PySide6``. Every function is pure (rows in, dict out), so it is fully
deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import profile_rows, infer_schema, validate_rows, load_rows

    rows = load_rows("export.csv")
    profile = profile_rows(rows)
    # profile["columns"]["age"] -> {count, null_count, null_fraction, distinct,
    #   unique, inferred_type, top_values, min, max, mean}

    schema = infer_schema(rows)        # validate_rows-compatible
    report = validate_rows(rows, schema)

``profile_rows`` returns ``{row_count, columns}`` where each column carries its
count, null count and fraction, distinct count, a uniqueness flag, the inferred
type (``int`` / ``number`` / ``bool`` / ``str``), the top values with counts,
and ``min`` / ``max`` / ``mean`` for numeric columns. ``infer_schema`` turns
that profile into a schema the existing ``validate_rows`` understands: a column
is ``required`` when it has no nulls, ``unique`` when every non-null value is
distinct, and carries numeric bounds. Pass an explicit ``columns`` list to
restrict either function to a subset.

Executor commands
-----------------

``AC_profile_rows`` profiles a ``rows`` list (optional ``columns`` subset) and
returns ``{profile}``. ``AC_infer_schema`` returns ``{schema}``. Both are
exposed as MCP tools (``ac_profile_rows`` / ``ac_infer_schema``) and as Script
Builder commands under **Data**.
