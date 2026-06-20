SARIF 2.1.0 Findings Export
===========================

The framework has several findings producers — action-lint, the secrets scan,
the WCAG/a11y audit, the guardrail — but no common export, so results couldn't
land in GitHub / Azure DevOps **code scanning** (the durable, deduplicated,
line-anchored alert store). SARIF 2.1.0 (OASIS) is that interchange format.

``to_sarif`` builds a SARIF document from a list of normalized *findings*
(``{rule_id, level, message, file?, line?}``), with adapters for the existing
lint / audit shapes and stable ``partialFingerprints`` so the same issue
deduplicates across runs. Pure standard library (``json`` + ``hashlib``);
imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        make_finding, to_sarif, write_sarif, from_lint_issues,
        from_audit_findings)

    findings = [
        make_finding("AC_SHELL", "shell command not allow-listed",
                     level="error", file="flow.json", line=12),
        *from_lint_issues(lint_issues, file="flow.json"),
        *from_audit_findings(wcag_report["findings"]),
    ]
    write_sarif(findings, "results.sarif", tool_name="AutoControl")
    # upload results.sarif via the GitHub "upload-sarif" action

``make_finding`` builds one normalized finding; ``from_lint_issues`` (maps
``index/severity/code/message``) and ``from_audit_findings`` (maps
``sc/criterion/kind/severity``) adapt the existing producers; ``to_sarif``
auto-derives the rule catalog and attaches a stable fingerprint per result;
``write_sarif`` serializes to a file. Severity strings map to SARIF
``error`` / ``warning`` / ``note``.

Executor command
----------------

``AC_export_sarif`` takes ``findings`` (a list, or JSON string) plus optional
``path`` and ``tool_name`` and returns ``{sarif, path?}``. The same operation is
exposed as the MCP tool ``ac_export_sarif`` and as a Script Builder command under
**Report**.
