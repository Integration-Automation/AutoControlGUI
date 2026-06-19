Just-In-Time Credential Leases
==============================

Long-lived secrets handed to automation are a standing liability. ``CredentialBroker``
applies **zero standing privilege**: a consumer takes a short-lived *lease* — a
token bound to a secret name with an expiry — and the real value is fetched only
at :meth:`redeem` time, only while the lease is valid, through a pluggable
*resolver* (an unlocked ``SecretManager``'s ``get``, an environment lookup, a
vault client). Expired or revoked leases yield nothing.

Secret values never enter executor/MCP records: the executor and MCP surfaces
manage the lease *lifecycle* only. :meth:`redeem`, which returns the real value,
is a deliberate **Python-API-only** escape hatch for code that must handle the
secret. The module is pure standard library and imports no ``PySide6``; the
clock and resolver are injectable, so expiry is deterministically testable.

Headless API
------------

.. code-block:: python

    from je_auto_control import CredentialBroker

    broker = CredentialBroker(resolver=secret_manager.get)   # resolver(name)->value
    token = broker.lease("db_password", ttl=120)             # token, not the value

    if broker.is_valid(token):
        password = broker.redeem(token)     # fetched just in time, Python-only
        connect(password)

    broker.revoke(token)                     # or let it expire after ttl seconds

``active()`` lists non-expired leases as ``{token, name, ttl_remaining}`` with no
values. A module-level :data:`default_broker` backs the executor/MCP commands;
configure its resolver once with ``set_secret_resolver(fn)``.

Executor commands
-----------------

================================ ===================================================
Command                          Effect
================================ ===================================================
``AC_lease_secret``              Issue a lease for ``name`` (``ttl`` s); ``{token, ttl}``.
``AC_lease_valid``               Report ``{valid}`` for a lease token.
``AC_revoke_lease``              Revoke a lease token; ``{revoked}``.
``AC_lease_active``              List active leases (no secret values).
================================ ===================================================

There is intentionally **no** redeem command on the executor, MCP, or Script
Builder surfaces — exposing the value there would leak it into run records.
Redeeming is Python-only. The same lifecycle operations are exposed as MCP tools
(``ac_lease_secret`` / ``ac_lease_valid`` / ``ac_revoke_lease`` /
``ac_lease_active``) and as Script Builder commands under **Tools**.
