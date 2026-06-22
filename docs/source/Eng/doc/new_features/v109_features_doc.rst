Confusable / Homoglyph Detection
================================

``secrets_scan`` finds secret-shaped tokens and ``guardrail`` screens text for
prompt injection, but nothing catches *visual* spoofing: a Cyrillic ``"а"``
(U+0430) is pixel-for-pixel a Latin ``"a"`` (U+0061), so ``"pаypal"`` (with a
Cyrillic ``а``) reads as ``"paypal"`` to a human yet compares unequal — the basis
of IDN-homograph phishing and lookalike UI labels.

Following the idea of Unicode TR39, this folds confusable characters to a
prototype *skeleton* (two strings are confusable when their skeletons match) and
flags strings that mix scripts. Pure standard library (``unicodedata``); imports
no ``PySide6``. Every function is pure, so it is fully deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        confusable_skeleton, is_confusable, detect_homoglyphs,
        is_mixed_script, scripts_of,
    )

    confusable_skeleton("pаypal")          # 'paypal'  (Cyrillic а -> a)
    is_confusable("pаypal", "paypal")      # True
    detect_homoglyphs("pаypal")            # [{'index': 1, 'char': 'а', 'prototype': 'a'}]
    is_mixed_script("pаypal")              # True  (Latin + Cyrillic)
    scripts_of("pаypal")                   # {'LATIN', 'CYRILLIC'}

``confusable_skeleton`` NFKC-normalises (folding fullwidth, ligatures and math
alphanumerics) then maps each remaining cross-script lookalike to its Latin
prototype. ``is_confusable`` is true only for *distinct* strings with equal
skeletons. ``detect_homoglyphs`` returns the offending characters with their
position and prototype. ``scripts_of`` / ``is_mixed_script`` classify characters
by Unicode block (ignoring digits, punctuation and spaces) so a single mixed-
script token can be flagged on its own.

Executor commands
-----------------

``AC_confusable_scan`` returns ``{skeleton, homoglyphs, mixed_script, scripts}``
for one string; ``AC_confusable_compare`` returns ``{confusable}`` for a pair.
Both are exposed as MCP tools (``ac_confusable_scan`` / ``ac_confusable_compare``)
and as Script Builder commands under **Data**.
