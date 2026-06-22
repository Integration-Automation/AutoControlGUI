Bidirectional-Text QA (Trojan-Source Scan)
==========================================

``confusables`` catches lookalike *characters*, but invisible Unicode
*directional formatting* is a separate hazard. The embeddings/overrides
(LRE/RLE/LRO/RLO/PDF), isolates (LRI/RLI/FSI/PDI) and marks (LRM/RLM/ALM) can
silently reorder how text renders. That is both an RTL localisation-QA gap and
the basis of the "Trojan Source" attack (CVE-2021-42574), where override controls
make source read differently than it runs.

This reports the bidi controls in a string, checks that embeddings/isolates are
balanced, infers the base direction, and flags Trojan-source-style formatting.
Pure standard library (``unicodedata``); imports no ``PySide6``. Every function is
pure, so it is fully deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        detect_bidi_issues, bidi_controls, has_bidi_controls,
        is_bidi_balanced, base_direction, is_trojan_source,
        strip_bidi_controls,
    )

    rlo, pdf = chr(0x202E), chr(0x202C)   # RLO override, PDF terminator
    sneaky = f"value = {rlo}admin{pdf}"
    detect_bidi_issues(sneaky)
    # {'controls': [{'index': 8, 'char': '<RLO>', 'name': 'RLO'}, ...],
    #  'has_controls': True, 'balanced': True, 'base_direction': 'LTR',
    #  'trojan_source': True}

    is_trojan_source(sneaky)        # True
    strip_bidi_controls(sneaky)     # 'value = admin'
    base_direction("אב") # 'RTL'  (Hebrew alef bet)

``bidi_controls`` lists every control as ``{index, char, name}``. ``is_bidi_balanced``
checks that PDF closes an embedding/override and PDI closes an isolate, properly
nested. ``base_direction`` returns ``LTR`` / ``RTL`` / ``NEUTRAL`` from the first
strong character. ``is_trojan_source`` is true when any non-mark formatting
control is present or the nesting is unbalanced. ``strip_bidi_controls`` returns a
clean copy. ``detect_bidi_issues`` bundles it all into one report.

Executor commands
-----------------

``AC_bidi_check`` returns the full report; ``AC_bidi_strip`` returns
``{text}`` with controls removed. Both are exposed as MCP tools
(``ac_bidi_check`` / ``ac_bidi_strip``) and as Script Builder commands under
**Data**.
