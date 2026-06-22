DMN-Style Decision Tables
=========================

Nested ``AC_if_var`` chains get unreadable fast. A decision table externalizes
branching into rows of ``conditions -> outputs`` evaluated by a **hit policy** —
the DMN way to keep business rules data-driven and reviewable.

Each cell condition is a wildcard (``None`` / ``"-"`` / ``"*"``), a literal
(equality), or ``{"op": "ge", "value": 18}`` using the project's standard
comparators (``eq/ne/lt/le/gt/ge/contains/startswith/endswith`` — reused from the
executor, not duplicated). Pure standard library; imports no ``PySide6``.

Hit policies
------------

================ ===================================================
Policy           Behavior
================ ===================================================
``UNIQUE``       Exactly one rule may match (raises if more do).
``FIRST``        The first matching rule wins.
``PRIORITY``     Same as FIRST — first match in rule order.
``COLLECT``      All matching rules' outputs (a list).
================ ===================================================

Headless API
------------

.. code-block:: python

    from je_auto_control import evaluate_table

    spec = {
        "inputs": ["age", "country"],
        "hit_policy": "FIRST",
        "rules": [
            {"conditions": {"age": {"op": "lt", "value": 18}},
             "outputs": {"tier": "minor"}},
            {"conditions": {"age": {"op": "ge", "value": 18}, "country": "US"},
             "outputs": {"tier": "us-adult"}},
            {"conditions": {"age": {"op": "ge", "value": 18}},
             "outputs": {"tier": "adult"}},
        ],
    }
    evaluate_table(spec, {"age": 30, "country": "DE"})   # -> {"tier": "adult"}

``evaluate_table`` returns the matched outputs dict (or ``{}`` if none) for
single-hit policies, and a list for ``COLLECT``. The ``DecisionTable`` class
(``from_dict`` / ``evaluate``) is available for reuse.

Executor command
----------------

``AC_decision_table`` takes ``spec`` and ``context`` (each a dict or JSON
string) and returns ``{result}``. The same operation is exposed as the MCP tool
``ac_decision_table`` and as a Script Builder command under **Flow**.
