JSON-Schema Compatibility Checking
==================================

We can *validate against* a JSON Schema (``json_schema``) and *generate* one
(``action_lint/schema``) but could not answer "will a consumer on the old
schema still read data written under the new schema?" — i.e. classify changes
(added-required field, removed field, narrowed type, removed enum value) under
the Confluent/Avro backward / forward / full rules. This adds that classifier.

Scope: the object-schema subset ``json_schema`` understands —
``properties`` / ``required`` / ``type`` / ``enum``. Pure standard library;
imports no ``PySide6``. Each function is pure (two schema dicts in, report out),
so it is fully deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        check_compatibility, is_backward_compatible, diff_schemas,
    )

    report = check_compatibility(old_schema, new_schema, mode="backward")
    # {"compatible": False, "mode": "backward",
    #  "changes": [...], "breaking": [{"path": "email", "kind": "field_added",
    #                                  "breaks": ["backward"]}]}

    if not is_backward_compatible(old_schema, new_schema):
        block_release()

``diff_schemas`` classifies every change as a ``SchemaChange`` (``path``,
``kind``, ``breaks``). Backward-breaking changes include a new required field, a
narrowed type, and a removed enum value; forward-breaking changes include a
removed required field, a widened type, and an added enum value.
``check_compatibility`` filters those by ``mode`` (``backward`` / ``forward`` /
``full``); ``is_backward_compatible`` / ``is_forward_compatible`` /
``is_full_compatible`` are boolean shortcuts.

Executor command
----------------

``AC_check_compatibility`` takes ``old`` / ``new`` schemas and an optional
``mode`` and returns ``{compatible, mode, changes, breaking}``. It is exposed as
the MCP tool ``ac_check_compatibility`` and as a Script Builder command under
**Data**.
