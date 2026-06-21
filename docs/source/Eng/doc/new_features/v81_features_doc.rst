Layered Configuration Resolver
==============================

``json_patch.merge_patch`` merges exactly two documents, ``config_sync``
resolves by last-write-wins timestamp, and ``AssetStore`` is flat per
environment. None of them compose an ordered ``defaults < file < env < CLI``
precedence stack with a deep dict merge, nor report *which layer won each key*.
This adds that 12-factor resolver.

Pure standard library (``copy``); imports no ``PySide6``. Layers are plain
mappings supplied by the caller (the env layer is passed in, never read from
``os.environ`` implicitly), so resolution is deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import LayeredConfig, deep_merge

    cfg = (LayeredConfig()
           .add_layer("defaults", {"db": {"host": "local", "port": 5432}})
           .add_layer("file", file_values, priority=10)
           .add_layer("env", env_values, priority=20))

    settings = cfg.resolve()                  # {"db": {"host": ..., "port": ...}}
    host = cfg.get("db.host")
    trace = cfg.explain("db.host")            # SourceTrace(value=..., layer="env")

``add_layer`` registers a named layer; higher ``priority`` wins (priority
defaults to insertion order, so later layers override earlier ones).
``resolve`` deep-merges every layer in ascending priority — nested dicts are
merged recursively while scalars and lists are replaced. ``get`` reads a dotted
key from the resolved config with a default; ``explain`` returns a
``SourceTrace`` naming the winning layer for a dotted key (raising ``KeyError``
when absent). ``deep_merge`` is exposed as a standalone two-mapping helper.

Executor commands
-----------------

``AC_resolve_config`` deep-merges a ``layers`` list (each ``{name, mapping,
priority?}``) into ``{config}``. ``AC_explain_config`` returns ``{trace}`` (the
value and winning layer) for a dotted ``key``. Both are exposed as MCP tools
(``ac_resolve_config`` / ``ac_explain_config``) and as Script Builder commands
under **Data**.
