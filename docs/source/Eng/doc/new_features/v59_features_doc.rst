OpenVEX Vulnerability Triage
============================

``scan_components`` (the OSV matcher) produces vulnerability findings, but every
known CVE then shows up on every run forever — there was no way to record "we
looked, this one does not affect us" and drop it. VEX (Vulnerability
Exploitability eXchange) is the standard for exactly that triage signal. This
authors `OpenVEX <https://openvex.dev>`_ 0.2.0 statements and applies them to
the scanner's findings.

``not_affected`` / ``fixed`` statements **suppress** a finding; ``affected`` /
``under_investigation`` **annotate** it with the assessed status. Statements
join to findings on the vulnerability id *or* any of its aliases, optionally
scoped to a product. Pure standard library (``hashlib`` + ``json`` +
``datetime``); imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        scan_components, vex_statement, build_vex, apply_vex)

    findings = scan_components(sbom["components"], advisories)

    statements = [
        vex_statement("CVE-2024-1", "not_affected",
                      products=["pkg:pypi/foo"],
                      justification="vulnerable_code_not_present"),
        vex_statement("GHSA-bar", "under_investigation"),
    ]
    vex = build_vex(statements, author="security@example.com")

    triaged = apply_vex(findings, vex)
    # CVE-2024-1 (not_affected) dropped; GHSA-bar kept with vex_status set

``vex_statement`` validates the inputs: ``status`` must be one of
``VEX_STATUSES`` (``not_affected`` / ``affected`` / ``fixed`` /
``under_investigation``); a ``not_affected`` statement must carry a
``justification`` (one of ``VEX_JUSTIFICATIONS``) or an ``impact_statement``.
``build_vex`` wraps statements in an OpenVEX document (pass an explicit
``timestamp`` for a reproducible ``@id``). ``apply_vex`` returns the surviving
findings, each non-suppressed match annotated with ``vex_status``.

Executor command
----------------

``AC_apply_vex`` takes ``findings`` and a ``vex`` document (each a list/object
or a JSON string) and returns ``{findings, count}`` of the survivors. The same
operation is exposed as the MCP tool ``ac_apply_vex`` and as a Script Builder
command under **Security**. It chains directly after ``AC_scan_vulns``.
