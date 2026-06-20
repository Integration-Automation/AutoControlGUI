JSON Schema Validation
======================

The framework only ever *generated* JSON Schema (action-lint, the tool-use
schema), and ``data_quality.validate_rows`` is a flat, per-column table checker —
neither can validate a nested API request/response body against a real schema.
This adds the missing consumer: validate an in-memory value against a JSON
Schema (Draft 2020-12 subset) and report **every** violation with a readable
path.

``validate_json`` returns a ``SchemaValidationResult`` (``ok`` plus an
``errors`` list of ``{path, keyword, message}``); ``is_valid`` is the boolean
shortcut; ``assert_schema`` raises ``AutoControlAssertionException`` with a
joined summary. Pure standard library (``re``); imports no ``PySide6``.

Supported keywords
------------------

* ``type`` — including ``integer`` matching integral floats (``5.0``) but never
  booleans; ``enum`` / ``const`` (keeping ``True`` and ``1`` distinct).
* numbers — ``minimum`` / ``maximum`` / ``exclusiveMinimum`` /
  ``exclusiveMaximum`` / ``multipleOf``.
* strings — ``minLength`` / ``maxLength`` / ``pattern``.
* arrays — ``minItems`` / ``maxItems`` / ``uniqueItems`` / ``items`` /
  ``prefixItems`` / ``contains``.
* objects — ``required`` / ``minProperties`` / ``maxProperties`` /
  ``properties`` / ``patternProperties`` / ``additionalProperties``.
* combinators — ``allOf`` / ``anyOf`` / ``oneOf`` / ``not``; boolean schemas
  (``True`` / ``False``); local ``$ref`` (``#/$defs/...`` JSON Pointer).

Remote ``$ref`` and ``format`` assertions are intentionally out of scope.

Headless API
------------

.. code-block:: python

    from je_auto_control import validate_json, is_valid, assert_schema

    schema = {
        "type": "object",
        "required": ["name", "age"],
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "age": {"type": "integer", "minimum": 0, "maximum": 130},
            "roles": {"type": "array", "items": {"enum": ["admin", "user"]},
                      "uniqueItems": True},
        },
    }

    result = validate_json({"name": "", "age": 200, "extra": 1}, schema)
    # result.ok is False
    for error in result.errors:
        print(error["path"], error["keyword"], "-", error["message"])
    # $.name minLength - shorter than 1
    # $.age  maximum   - greater than maximum 130
    # $.extra additionalProperties - additional property not allowed

    if is_valid(payload, schema):
        ...                         # boolean shortcut

    assert_schema(payload, schema)  # raises on the first invalid value

This pairs naturally with the existing ``json_query`` (extract a value) and the
``http_request`` helper (validate an API response body before acting on it).

Executor command
----------------

``AC_validate_json`` takes ``data`` and ``schema`` (each a list/object, or a
JSON string) and returns ``{ok, errors}``. The same operation is exposed as the
MCP tool ``ac_validate_json`` and as a Script Builder command under **Data**.
