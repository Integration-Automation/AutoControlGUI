==================================================
New Features (2026-06-19) — i18n / l10n Testing
==================================================

Three pure-standard-library internationalization / localization testing
helpers that compound, wired through the full stack (facade, ``AC_*``
executor commands, MCP tools, Script Builder).

.. contents::
   :local:
   :depth: 2


Pseudo-localization
==================

Accent and pad UI strings (preserving placeholders) to flush out hardcoded
text and pre-stress layout *before* any real translation exists::

    from je_auto_control import pseudo_localize, pseudo_localize_catalog

    pseudo_localize("Hello {name}")        # "⟦Hèllo {name}········⟧"
    pseudo_localize_catalog({"save": "Save", "cancel": "Cancel"})

Placeholders (``{name}`` / ``{{x}}`` / ``%s`` / ``%d``) are preserved
verbatim; ``expansion`` controls the padding fraction; the ``⟦…⟧`` brackets
make truncation visible. Exposed as ``AC_pseudo_localize`` /
``ac_pseudo_localize``. Untranslated (un-accented) strings in a screen are a
sign of unexternalized, hardcoded text.


Text-overflow detection
=======================

Flag text whose estimated width exceeds its widget bounds — the #1
localization bug (German/Finnish expand 30–50%). Computed from the
accessibility bounds AutoControl already reads::

    from je_auto_control import check_overflow

    issues = check_overflow(elements, avg_char_px=7.0)
    # [{"text": "...", "width": 40, "required_px": 400.0, "overflow_px": 360.0}]

Width is estimated as ``len(text) * avg_char_px`` (deterministic
heuristic). Exposed as ``AC_check_overflow`` / ``ac_check_overflow`` (uses
the live a11y tree unless ``elements`` are supplied).


Catalog completeness
===================

Diff a translation catalog against a base locale for missing / orphaned /
empty keys and placeholder mismatches — a CI gate against blank UI::

    from je_auto_control import check_catalog

    report = check_catalog(base_locale, target_locale)
    report["missing"]               # keys absent in target
    report["placeholder_mismatch"]  # e.g. "{count}" dropped in the target

Exposed as ``AC_check_catalog`` / ``ac_check_catalog``.
