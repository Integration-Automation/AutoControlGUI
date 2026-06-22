Dependency Vulnerability Scanning (OSV)
=======================================

``build_sbom`` *inventories* dependencies and ``to_sarif`` *exports* findings,
but nothing in between ever **produced** a vulnerability finding — there was no
advisory matching at all. This closes that loop: given the SBOM's
``(ecosystem, name, version)`` components and an `OSV <https://osv.dev>`_
advisory database, ``scan_components`` reports which packages are affected, and
``findings_to_sarif`` bridges the results straight into the existing SARIF
exporter for GitHub / Azure DevOps code scanning.

The advisory database is **injected as plain data** (a list of OSV records), so
matching is fully offline and deterministic; the live ``osv.dev`` query is a
separate, optional ``fetcher`` seam. Pure standard library (``re``); imports no
``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        build_sbom, scan_components, findings_to_sarif, write_sarif)

    advisories = [{
        "id": "GHSA-foo", "summary": "RCE in foo",
        "database_specific": {"severity": "HIGH"},
        "affected": [{
            "package": {"ecosystem": "PyPI", "name": "foo"},
            "ranges": [{"type": "ECOSYSTEM",
                        "events": [{"introduced": "0"}, {"fixed": "1.2.0"}]}],
        }],
    }]

    sbom = build_sbom("je_auto_control")
    findings = scan_components(sbom["components"], advisories)
    # findings: [{id, package, version, summary, severity, fixed, aliases}]
    write_sarif(findings_to_sarif(findings), "vulns.sarif",
                tool_name="AutoControl-VulnScan")

``is_affected(version, osv_range)`` evaluates one OSV range by sweeping its
``introduced`` / ``fixed`` / ``last_affected`` events; ``match_package`` checks
a single package against the database (explicit ``versions`` **or** ranges);
``scan_components`` runs the whole SBOM. Package names are compared with PEP-503
normalization, and the OSV severity word (``CRITICAL`` / ``HIGH`` /
``MODERATE`` / ``LOW``) maps to a SARIF ``error`` / ``warning`` / ``note``
level (defaulting to ``warning``).

Version ordering is a pragmatic numeric comparison: release components compare
as integers and a pre-release suffix (``1.2.0-rc1``) sorts before the final
release. Git ranges and full CVSS-vector scoring are out of scope.

Live advisories (optional)
--------------------------

Pass a ``fetcher`` callable to pull advisories at scan time (e.g. from the
``osv.dev`` API). Tests inject a fake fetcher, so the matching logic is verified
without any network:

.. code-block:: python

    findings = scan_components(sbom["components"], None,
                              fetcher=my_osv_fetcher)

Executor command
----------------

``AC_scan_vulns`` takes ``components`` (a component list, a full SBOM dict, or a
JSON string) and ``advisories`` (a list or JSON string), with an optional
``sarif_path`` to write a SARIF report; it returns ``{findings, count}`` (plus
``sarif_path`` when written). The same operation is exposed as the MCP tool
``ac_scan_vulns`` and as a Script Builder command under **Security**.
