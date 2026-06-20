JSONPath Querying
=================

The executor's built-in path walker only splits on ``.`` and indexes — it can't
do wildcards, recursive descent, or filters, so API/DB responses with arrays are
awkward to extract from. ``json_query`` adds a focused JSONPath subset over
already-parsed JSON:

================ ===================================================
Syntax           Meaning
================ ===================================================
``$``            root (optional prefix)
``.name``        member access
``[n]`` ``[-n]`` list index (negative from the end)
``*`` ``[*]``    wildcard (all members / elements)
``..``           recursive descent
``[?(@.k op v)]`` filter array elements (``op`` ∈ ``== != < <= > >=``)
================ ===================================================

Pure standard library (``re``); imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import json_query, json_query_one, json_extract

    json_query(data, "$.store.books[*].title")          # every title
    json_query(data, "$.store.books[?(@.price > 8)].title")  # filtered
    json_query(data, "$..price")                         # recursive descent

    json_query_one(data, "$.user.name", default="?")     # first match or default
    json_extract(data, {"name": "$.user.name",           # mapping -> flat dict
                        "first_tag": "$.tags[0]"})

``json_query`` returns **all** matches (a list); ``json_query_one`` returns the
first (or a default); ``json_extract`` runs a ``{key: path}`` mapping into a flat
dict (first match per path). This is the path engine the existing
``AC_http_to_var`` / API / DB-row flows were missing.

Executor commands
-----------------

================================ ===================================================
Command                          Effect
================================ ===================================================
``AC_json_query``                ``{matches}`` — all values matching a JSONPath.
``AC_json_extract``              ``{result}`` — a ``{key: path}`` mapping extracted.
================================ ===================================================

``data`` (and ``mapping``) accept a JSON object or a JSON string (so the visual
builder works). The same operations are exposed as MCP tools (``ac_json_query`` /
``ac_json_extract``) and as Script Builder commands under **Data**.
