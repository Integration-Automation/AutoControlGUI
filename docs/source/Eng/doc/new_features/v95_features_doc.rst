Typed Configuration Schema
==========================

``assets._coerce`` coerces a single value and ``json_schema`` validates JSON
structure, but nothing bound a resolved config dict into a typed object with
required-field enforcement and choice constraints. This validates a mapping
against declared fields, coercing types and reporting actionable errors — a
stdlib analog of pydantic-settings.

Pure standard library (``dataclasses``); imports no ``PySide6``. Validation is a
function of the mapping and the ``environ`` it is given (default ``os.environ``);
pass ``environ={}`` to make it fully deterministic in CI.

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
optional ``default``, ``required`` flag, ``choices``, and an ``env`` variable
name. A value comes from the mapping, else from that variable, else from the
default (the pydantic-settings order); an ``int`` field refuses a float with a
fraction instead of truncating it. ``ConfigSchema.validate`` coerces each value, applies defaults, enforces
required fields and choices, and returns ``{ok, config, errors}`` (errors as
``{field, error}``). ``ConfigSchema.from_dict`` builds a schema from a plain
spec, ``validate_config`` does spec-plus-mapping in one call, and ``coerce``
exposes the value coercion (booleans accept ``true``/``yes``/``on`` etc.).

Executor command
----------------

``AC_validate_config`` validates a ``config`` mapping against a ``schema`` spec
and returns ``{ok, config, errors}``. It is exposed as the MCP tool
``ac_validate_config`` and as a Script Builder command under **Data**.
