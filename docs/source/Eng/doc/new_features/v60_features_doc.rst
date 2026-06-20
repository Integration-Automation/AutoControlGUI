License Policy Gate
===================

``build_sbom`` records each component's license *name*, but nothing ever judged
it — a copyleft or otherwise-disallowed license could ship unnoticed. This adds
the policy gate: normalize the SBOM's license strings to SPDX ids, evaluate them
against an allowlist / denylist (with a built-in strong-copyleft set), and emit
violations that bridge into the existing SARIF exporter — the license-compliance
lane beside the OSV vulnerability lane.

Pure standard library (``re``); fully offline; imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        build_sbom, evaluate_sbom, evaluate_license,
        license_findings_to_sarif, write_sarif, DEFAULT_COPYLEFT)

    sbom = build_sbom("je_auto_control")

    # Allowlist mode: anything outside the list is a violation.
    violations = evaluate_sbom(sbom["components"],
                               allow=["MIT", "Apache-2.0", "BSD-3-Clause"])

    # Or denylist mode using the built-in strong-copyleft set.
    violations = evaluate_sbom(sbom["components"], deny=DEFAULT_COPYLEFT)

    write_sarif(license_findings_to_sarif(violations), "licenses.sarif",
                tool_name="AutoControl-License")

``normalize_spdx`` maps loose names (``"MIT License"`` → ``MIT``, ``"Apache
2.0"`` → ``Apache-2.0``) to SPDX ids. ``evaluate_license`` returns ``allowed`` /
``denied`` / ``unknown``: ``deny`` takes precedence; an empty ``allow`` means
"not constrained"; a missing license is ``unknown``. SPDX **expressions** are
understood — ``"MIT OR GPL-3.0-only"`` is a *choice* (allowed if any operand is
allowed), while ``"MIT AND GPL-3.0-only"`` requires every operand. Each
violation is ``{name, version, license, status}``; ``denied`` maps to a SARIF
``error`` and ``unknown`` to a ``warning``.

Executor command
----------------

``AC_check_licenses`` takes ``components`` (a component list, a full SBOM dict,
or a JSON string) and optional ``allow`` / ``deny`` lists; it returns
``{violations, count}``. The same operation is exposed as the MCP tool
``ac_check_licenses`` and as a Script Builder command under **Security**.
