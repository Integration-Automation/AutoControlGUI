==================================================
New Features (2026-06-19) — WCAG 2.2 Audit Engine
==================================================

The accessibility audit gains a **WCAG 2.2 / EN 301 549 success-criterion
layer**: each defect is tagged with the WCAG criterion it violates (id +
name + conformance level + impact), and a new WCAG 2.2 rule — **Target
Size (Minimum), SC 2.5.8** — is computed from element bounds. The result is
a conformance-style report you can map to EN 301 549 for accessibility
compliance evidence (the European Accessibility Act is enforceable since
June 2025). Pure standard library; wired through the full stack.

.. contents::
   :local:
   :depth: 2


Conformance audit
================

::

    from je_auto_control import wcag_audit

    report = wcag_audit(level="AA")          # live a11y tree
    report = wcag_audit(elements=els,        # or supply elements/colours/text
                        contrast_pairs=pairs, texts=ocr_texts, level="AA")

    report["conformant"]      # True when no findings at the requested level
    report["by_criterion"]    # {"1.4.3 Contrast (Minimum)": 2, ...}
    report["findings"]        # each tagged {sc, criterion, level, impact, ...}

Findings are filtered to the requested conformance ``level`` (``A`` /
``AA`` / ``AAA``). Mapped success criteria:

* **1.1.1 / 4.1.2** — interactive element with no accessible name.
* **1.4.3 Contrast (Minimum)** — foreground/background below the ratio.
* **1.4.10 Reflow** — clipped / truncated text.
* **2.5.8 Target Size (Minimum)** — *new in 2.2*: pointer targets smaller
  than 24x24 px.


Target Size rule
===============

``audit_target_size(elements, min_px=24)`` flags interactive elements whose
bounds are smaller than ``min_px`` on either side (elements with unknown
size are skipped). ``tag_issue(issue)`` annotates any base ``AuditIssue``
with its success criterion, so existing audits gain SC tagging too.

Exposed as ``AC_wcag_audit`` / ``ac_wcag_audit`` (and ``wcag_audit`` /
``audit_target_size`` on the package facade).
