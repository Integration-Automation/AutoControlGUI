String-Distance Similarity Metrics
==================================

``fuzzy`` exposes only difflib's gestalt ratio. This adds the edit-distance and
token-set metrics it lacks — Levenshtein / Damerau-Levenshtein, Jaro and
Jaro-Winkler (the standard for short names and labels), and character-n-gram
Jaccard / Dice — for better matching of typos and reordered tokens, especially
from OCR.

Pure standard library; imports no ``PySide6``. Every function is pure (two
strings in, a number out), so it is fully deterministic in CI. Pair with
``normalize_text`` to make matches accent- and form-insensitive first.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        levenshtein, damerau_levenshtein, jaro_winkler, jaccard, dice,
        similarity, normalize_text,
    )

    levenshtein("kitten", "sitting")            # 3
    damerau_levenshtein("ab", "ba")             # 1 (transposition)
    jaro_winkler("MARTHA", "MARHTA")            # ~0.961
    jaccard("night", "nacht", n=2)              # char-bigram overlap

    # normalised [0, 1] score for any metric (edit distance -> 1 - d/max_len):
    similarity(normalize_text(a), normalize_text(b), metric="jaro_winkler")

``levenshtein`` / ``damerau_levenshtein`` return integer edit distances (the
latter counting an adjacent transposition as one edit). ``jaro`` / ``jaro_winkler``
and ``jaccard`` / ``dice`` return ``[0, 1]`` similarities. ``similarity`` is the
unified entry point — it returns the Jaro/Jaccard/Dice metrics directly and
converts edit distances to ``1 - distance / max_len`` so every metric is
comparable on the same scale.

Executor command
----------------

``AC_text_similarity`` returns ``{score}`` for two strings ``a`` / ``b`` and an
optional ``metric``. It is exposed as the MCP tool ``ac_text_similarity`` and as
a Script Builder command under **Data**.
