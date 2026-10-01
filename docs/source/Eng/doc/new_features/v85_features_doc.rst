URI-Scheme Value References
===========================

``script_vars.interpolate`` hardcodes a single indirection (``${secrets.NAME}``
→ vault) and ``AssetStore`` credential references are vault-name-only. There was
no general, pluggable read-time indirection — the modern config pattern of
storing a *pointer* (``env://TOKEN``, ``file://./token``, ``secret://api-key``)
rather than the value. This adds that resolver.

Pure standard library (``os`` / ``re``); imports no ``PySide6``. The env reader,
secret resolver, and base directory are injectable, so resolution is safe and
deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import resolve_ref, resolve_refs_in, RefResolver

    token = resolve_ref("env://API_TOKEN")
    key = resolve_ref("file://./secrets/key.pem")

    config = resolve_refs_in({
        "token": "env://API_TOKEN",
        "db": {"password": "secret://db-password"},
    })

``resolve_ref`` resolves one reference: ``env://`` reads an environment variable
(from an injectable mapping, falling back to ``os.environ``), ``file://`` reads a
file (a relative path is relative to the optional ``base_dir``, which also
refuses any path that resolves outside it), and
``secret://`` delegates to an injectable resolver or the governance credential
broker. ``resolve_refs_in`` walks a nested dict/list and resolves every
reference in place, leaving non-reference values untouched. ``is_ref`` tests a
value, and ``RefResolver`` bundles the injectable backends for repeated use.
Unresolvable or unknown-scheme references raise ``SecretRefError``.

Executor commands
-----------------

``AC_resolve_ref`` resolves a single ``ref`` into ``{value}``;
``AC_resolve_refs`` resolves every reference inside ``obj`` and returns
``{resolved}``. Both are exposed as MCP tools (``ac_resolve_ref`` /
``ac_resolve_refs``) and as Script Builder commands under **Security**.
Their results are recorded (the executor record, the MCP result), so they
refuse ``secret://`` with ``SecretRefError``: secret values never enter those
records. Reference ``${secrets.NAME}`` in the step that needs the value, or call
``resolve_ref`` from Python.
