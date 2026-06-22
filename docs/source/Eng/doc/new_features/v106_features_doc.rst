Optimistic-Concurrency Versioned Store
======================================

``http_conditional`` uses ETag for *read* caching (``If-None-Match`` / 304) but
never for *write* concurrency (``If-Match`` / version check). There was no local
compare-and-swap / versioned record store for "update only if the version is
unchanged". This fills the write side of the ETag story.

Pure standard library (``json``); imports no ``PySide6``. The version is a
monotonic int and the store is in-memory with JSON persistence, so behaviour is
fully deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import VersionedStore, VersionConflict, if_match_header

    store = VersionedStore()
    version = store.put("db.host", "prod-1")          # version 1
    record = store.get("db.host")                      # {"value": ..., "version": 1}
    try:
        store.put("db.host", "prod-2", expected_version=record["version"])
    except VersionConflict:
        reload_and_retry()
    header = if_match_header(version)                  # '"1"' for an HTTP If-Match

``put`` writes only when ``expected_version`` matches the current version
(``0`` requires the key to be absent, omitting it is a blind write) and returns
the new version, raising ``VersionConflict`` on a stale write. ``get`` returns
``{value, version}``; ``delete`` is likewise guarded; ``save`` / ``load``
persist as JSON. ``if_match_header`` / ``check_if_match`` bridge to real HTTP
``If-Match`` writes alongside ``http_conditional``.

Executor commands
-----------------

``AC_cas_put`` returns ``{ok, version}`` (or ``{ok: false, error}`` on conflict);
``AC_cas_get`` returns ``{record}``. Both use a named-instance registry and are
exposed as MCP tools (``ac_cas_put`` / ``ac_cas_get``) and as Script Builder
commands under **Flow**.
