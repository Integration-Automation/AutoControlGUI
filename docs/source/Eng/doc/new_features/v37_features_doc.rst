Compliance Control Report (SOC2 / ISO 27001)
============================================

AutoControl already ships the *controls* an auditor cares about — a network
egress allowlist, just-in-time credential leases, maker-checker approval, a
secrets scanner, audit logging, a CycloneDX SBOM. :func:`build_compliance_report`
turns "are those controls in place?" into an auditor-readable **control evidence
report**: you supply a flat ``evidence`` mapping of observed facts, and each
catalogued control is marked ``satisfied`` / ``gap`` / ``not_assessed``.

It is a reporting *aid*, not a certification — it records the evidence you
assert, it does not itself verify the controls. Pure standard library; imports
no ``PySide6``.

Mapped controls
---------------

================ ============= =================================================== ==============================
Framework        Control       Title                                               Evidence key
================ ============= =================================================== ==============================
SOC2             CC6.1         Logical access restricted to authorized hosts       ``egress_allowlist_enforced``
SOC2             CC6.3         Least-privilege, time-boxed credentials             ``jit_credentials_used``
SOC2             CC6.8         Secrets not hardcoded and scanned                   ``secrets_scanned``
SOC2             CC7.3         Security events logged for review                   ``audit_logging_enabled``
SOC2             CC8.1         Changes require segregated (maker-checker) approval  ``change_approval_required``
ISO 27001        A.5.23        Information security for cloud/network egress       ``egress_allowlist_enforced``
ISO 27001        A.8.16        Monitoring activities / audit trail                 ``audit_logging_enabled``
ISO 27001        A.8.30        Software bill of materials maintained               ``sbom_generated``
================ ============= =================================================== ==============================

Headless API
------------

.. code-block:: python

    from je_auto_control import build_compliance_report, write_compliance_report

    report = build_compliance_report({
        "egress_allowlist_enforced": True,
        "jit_credentials_used": True,
        "secrets_scanned": True,
        "audit_logging_enabled": True,
        "change_approval_required": True,
        "sbom_generated": True,
    }, frameworks=["SOC2"])          # frameworks is optional

    print(report["summary"])         # {satisfied, gap, not_assessed, total}
    write_compliance_report(report, "build/compliance.html", fmt="html")

A control is ``satisfied`` when its evidence key is truthy, ``gap`` when
explicitly falsy, and ``not_assessed`` when the key is absent — so a partial
evidence dict produces an honest gap analysis. ``render_compliance_html`` returns
a standalone HTML table; ``write_compliance_report`` writes ``json`` or ``html``.

Executor command
----------------

``AC_compliance_report`` takes ``evidence`` (a JSON object, or JSON string from
the visual builder), an optional ``frameworks`` list/comma-string, and optional
``path`` + ``fmt`` to write a file; it returns ``{summary, controls, path?}``.
The same operation is exposed as the MCP tool ``ac_compliance_report`` and as a
Script Builder command under **Report**.
