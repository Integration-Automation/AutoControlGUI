Referential Integrity Checks
============================

``data_quality.validate_rows`` is strictly intra-row, single-table — its
``unique`` rule only dedupes within one batch. There was no parent/child
foreign-key check across two loaded tables, no composite-key uniqueness, and no
standalone accepted-values / row-count assertion. This adds those dbt-style
generic checks over rows already loaded by ``load_rows`` / ``query_sqlite``.

Pure standard library (``collections``); imports no ``PySide6``. Every function
is pure (rows in, report out), so it is fully deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        check_foreign_key, check_unique_key, check_accepted_values,
        check_row_count, load_rows,
    )

    orders = load_rows("orders.csv")
    users = load_rows("users.csv")

    fk = check_foreign_key(orders, "user_id", users, "id")   # {ok, violations, missing}
    pk = check_unique_key(orders, ["region", "id"])          # {ok, duplicates}
    av = check_accepted_values(orders, "status", ["open", "closed"])
    rc = check_row_count(orders, minimum=1)                  # {ok, count}

``check_foreign_key`` flags non-null child values absent from the parent column
(dbt ``relationships``). ``check_unique_key`` reports duplicate single or
composite keys. ``check_accepted_values`` lists non-null values outside the
allowed set. ``check_row_count`` verifies the count falls within optional
``minimum`` / ``maximum`` bounds. Each returns an ``ok`` flag plus details.

Executor commands
-----------------

``AC_check_foreign_key``, ``AC_check_unique_key``, ``AC_check_accepted_values``,
and ``AC_check_row_count`` each take JSON ``rows`` (and a column / key / allowed
list) and return the report. All are exposed as MCP tools
(``ac_check_*``) and as Script Builder commands under **Data**.
