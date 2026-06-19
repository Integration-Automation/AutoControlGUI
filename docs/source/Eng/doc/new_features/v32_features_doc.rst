Maker-Checker Approval Gate
===========================

Some automation steps are too consequential to fire on one party's say-so —
deleting production data, wiring money, promoting a release. ``ApprovalGate``
adds a **segregation of duties** control: a *maker* files a request and gets a
token; a *checker*, who must be a **different** principal, approves or rejects
it; the action proceeds only once the token is approved.

State is an optional JSON file, so the maker (e.g. a CI dispatcher) and the
checker (e.g. a human approver) can run as separate processes. The module is
pure standard library and imports no ``PySide6``; tokens use :mod:`secrets`.

Headless API
------------

.. code-block:: python

    from je_auto_control import ApprovalGate

    gate = ApprovalGate("approvals.json")          # shared across processes
    token = gate.request("delete prod table", requester="alice")

    # Self-approval is refused — the checker must differ from the maker.
    gate.approve(token, "alice")    # -> False
    gate.approve(token, "bob")      # -> True

    if gate.is_approved(token):
        run_high_risk_action()

``reject(token, approver)`` blocks an action; a request that has already been
decided cannot be re-decided. ``status(token)`` returns
``pending`` / ``approved`` / ``rejected`` (or ``None`` for an unknown token),
``get(token)`` returns the full record, and ``pending()`` lists every request
still awaiting a decision.

Executor commands
-----------------

================================ ===================================================
Command                          Effect
================================ ===================================================
``AC_approval_request``          File a request for ``action``; returns ``{token}``.
``AC_approval_approve``          Approve ``token`` as ``approver``; ``{approved}``.
``AC_approval_reject``           Reject ``token`` as ``approver``; ``{rejected}``.
``AC_approval_status``           Return ``{status, approved}`` to gate an action.
================================ ===================================================

Each command accepts an optional ``db`` path so a flow can persist requests to
a shared JSON file. The same operations are exposed as MCP tools
(``ac_approval_request`` / ``ac_approval_approve`` / ``ac_approval_reject`` /
``ac_approval_status``) and as Script Builder commands under **Tools**.
