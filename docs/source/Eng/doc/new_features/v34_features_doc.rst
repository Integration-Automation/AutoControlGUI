Network Egress Allowlist Guard
==============================

Unattended automation that can reach arbitrary hosts is an exfiltration risk.
``EgressPolicy`` lets an operator pin which hosts the headless HTTP client may
talk to. It is consulted by every
:func:`~je_auto_control.utils.http_client.http_client.http_request` call (and
therefore by ``AC_http`` and every feature built on it), so locking egress down
covers the whole framework at once.

The policy supports an **allow** list (default-deny — only matching hosts pass)
and/or a **deny** list (block these even when otherwise allowed). Patterns are
case-insensitive :mod:`fnmatch` globs over the URL hostname, e.g.
``*.example.com`` or ``localhost``. The module-level policy starts in
*allow-all* mode, so there is **no behavior change** until an operator locks it
down. Pure standard library; imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import set_egress_policy, EgressBlocked, http_request

    set_egress_policy(allow=["*.internal.corp", "api.example.com"])

    http_request("https://api.example.com/v1")     # ok
    try:
        http_request("https://evil.test/")          # raises before connecting
    except EgressBlocked:
        ...

    set_egress_policy(None, None)                    # back to allow-all

Modes: ``allow=None`` is allow-all; ``allow=[]`` denies everything;
``deny=[...]`` alone blocks just those hosts. ``allow`` / ``deny`` each accept a
list or a single comma-separated string. ``get_egress_policy().is_allowed(url)``
checks a URL without raising; ``EgressPolicy(allow=..., deny=...)`` builds an
independent policy object.

Executor commands
-----------------

================================ ===================================================
Command                          Effect
================================ ===================================================
``AC_egress_allow``              Lock the HTTP client to ``allow`` / ``deny`` lists.
``AC_egress_check``              Report ``{allowed}`` for a URL (does not raise).
``AC_egress_reset``              Clear the policy back to allow-all.
================================ ===================================================

The same operations are exposed as MCP tools (``ac_egress_allow`` /
``ac_egress_check`` / ``ac_egress_reset``) and as Script Builder commands under
**Tools**.
