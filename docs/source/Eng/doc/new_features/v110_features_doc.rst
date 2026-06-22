Readability Scoring
===================

The text utilities canonicalise (``text_normalize``), match (``text_similarity``,
``fuzzy``) and rank (``search_index``) text, but nothing scores *how hard it is
to read*. There was no way to assert that an on-screen message, a generated label
or a doc string stays within a target reading grade. This adds the classic
English readability formulae over a deterministic tokeniser and syllable
heuristic.

Pure standard library (``re`` / ``math``); imports no ``PySide6``. Every function
is pure (text in, number/report out), so it is fully deterministic in CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        flesch_reading_ease, flesch_kincaid_grade, gunning_fog, smog_index,
        automated_readability_index, readability_report, readability_stats,
        count_syllables,
    )

    flesch_reading_ease("The cat sat on the mat.")     # ~116 (very easy)
    flesch_kincaid_grade(marketing_copy)               # US grade level
    readability_report(text)                           # every metric + counts

    # gate generated UI copy on a reading grade
    assert flesch_kincaid_grade(label) <= 8

``readability_stats`` returns the raw counts (``words``, ``sentences``,
``syllables``, ``characters``, ``complex_words``) shared by every formula.
``flesch_reading_ease`` is higher-is-easier (~0-100 for normal prose); the others
(Flesch-Kincaid, Gunning Fog, SMOG, ARI) return a US grade level. ``count_syllables``
is the heuristic vowel-group counter (with silent-``e`` and consonant-``le``
handling) the formulae build on. ``readability_report`` bundles all five metrics
plus the stats into one dict.

Executor commands
-----------------

``AC_readability_report`` returns the full report (all five metrics plus counts)
for a string. It is exposed as the MCP tool ``ac_readability_report`` and as a
Script Builder command under **Data**.
