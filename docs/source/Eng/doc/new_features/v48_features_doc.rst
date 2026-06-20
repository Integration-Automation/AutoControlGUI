Environment-Scoped Typed Asset Store
====================================

Flows need centrally-managed config values that differ by environment
(dev/staging/prod) and carry a type — the orchestrator "Assets / lockers"
pillar. The secret vault covers secrets only and config-sync moves whole blobs;
neither offers a typed, per-environment named lookup. ``AssetStore`` fills that:
values are stored under an environment, read back with type coercion, and
``credential`` assets hold a *reference* (a secret name) that :meth:`resolve`
turns into the real value through an injected resolver — so the secret never
lands in a plain ``get`` or an executor record.

JSON-backed (or in-memory); pure standard library; imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import AssetStore, active_environment

    store = AssetStore("assets.json")
    store.set("max_retries", 3, type="int", environment="prod")
    store.set("api_base", "https://prod.example.com", environment="prod")
    store.set("db_password", "vault_db_pw", type="credential")  # value = a ref

    store.get("max_retries", environment="prod").value     # -> 3 (typed)
    store.get("api_base", environment="staging").value     # -> falls back to default
    store.get("db_password").value                         # -> "vault_db_pw" (reference, safe)

    # resolve a credential through an injected secret resolver (Python-only):
    store = AssetStore("assets.json", secret_resolver=secret_manager.get)
    store.resolve("db_password")                           # -> the real secret

Types are ``text`` / ``int`` / ``bool`` / ``credential``; ``get`` coerces to the
declared type and falls back to the ``default`` environment unless disabled.
``active_environment()`` reads ``JE_AUTOCONTROL_ENV``. ``list`` / ``delete`` round
out the store.

Executor commands
-----------------

================================ ===================================================
Command                          Effect
================================ ===================================================
``AC_set_asset``                 Store a typed, environment-scoped asset.
``AC_get_asset``                 Read an asset (credential stays a reference).
``AC_list_assets``               List ``{name, type, environment}`` (no values).
================================ ===================================================

Credential **resolution** is intentionally Python-API-only (so secrets never
enter run records). The same lifecycle operations are exposed as MCP tools
(``ac_set_asset`` / ``ac_get_asset`` / ``ac_list_assets``) and as Script Builder
commands under **Data**.
