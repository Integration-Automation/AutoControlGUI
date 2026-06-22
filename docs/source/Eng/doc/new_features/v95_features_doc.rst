Typed Configuration Schema
==========================

``assets._coerce`` coerces a single value and ``json_schema`` validates JSON
structure, but nothing bound a resolved config dict into a typed object with
required-field enforcement and choice constraints. This validates a mapping
against declared fields, coercing types and reporting actionable errors — a
stdlib analog of pydantic-settings.

Pure standard library (``dataclasses``); imports no ``PySide6``. Validation is a
pure function (mapping in, report out), so it is fully deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import ConfigSchema, ConfigField, validate_config

    schema = ConfigSchema({
        "port": ConfigField("int", required=True),
        "env": ConfigField("str", default="dev", choices=["dev", "prod"]),
        "debug": ConfigField("bool", default=False),
    })
    report = schema.validate({"port": "8080", "debug": "yes"})
    # {"ok": True, "config": {"port": 8080, "env": "dev", "debug": True}, "errors": []}

``ConfigField`` declares a ``type`` (``str`` / ``int`` / ``float`` / ``bool``),
optional ``default``, ``required`` flag, ``choices``, and an ``env`` hint.
``ConfigSchema.validate`` coerces each present value, applies defaults, enforces
required fields and choices, and returns ``{ok, config, errors}`` (errors as
``{field, error}``). ``ConfigSchema.from_dict`` builds a schema from a plain
spec, ``validate_config`` does spec-plus-mapping in one call, and ``coerce``
exposes the value coercion (booleans accept ``true``/``yes``/``on`` etc.).

Executor command
----------------

``AC_validate_config`` validates a ``config`` mapping against a ``schema`` spec
and returns ``{ok, config, errors}``. It is exposed as the MCP tool
``ac_validate_config`` and as a Script Builder command under **Data**.
