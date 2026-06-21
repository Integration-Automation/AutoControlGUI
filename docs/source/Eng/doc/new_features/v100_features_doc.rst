Near-Duplicate Text Detection (SimHash / MinHash)
=================================================

``fuzzy.fuzzy_dedupe`` is O(n²) pairwise ``SequenceMatcher`` with no stable
fingerprint, and ``image_dedup`` only hashes pixels. This adds text
fingerprints — SimHash (Hamming-distance near-dup) and MinHash (estimated
Jaccard) — that scale and give a reusable signature, the text analog of the
perceptual image hash.

Pure standard library (``hashlib`` / ``re``); imports no ``PySide6``. A fixed
hash (``blake2b``, not the salted built-in ``hash()``) keeps fingerprints
deterministic across runs and CI.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        simhash, near_duplicates, minhash_signature, minhash_similarity,
    )

    h1 = simhash("the quick brown fox jumps over the lazy dog")
    h2 = simhash("the quick brown fox jumps over the lazy dogs")
    # small Hamming distance ⇒ near-duplicate

    clusters = near_duplicates(docs, max_distance=12)   # groups of indices

    sig_a = minhash_signature(text_a)
    minhash_similarity(sig_a, minhash_signature(text_b))  # ~ Jaccard

``simhash`` returns a ``bits``-wide fingerprint from word shingles;
``hamming_distance`` (shared with ``image_dedup``) measures bit difference.
``near_duplicates`` clusters texts whose SimHashes are within ``max_distance``
bits, returning a partition of indices (singletons included).
``minhash_signature`` / ``minhash_similarity`` give a MinHash signature and a
Jaccard estimate for set-overlap style dedup. Run ``normalize_text`` first for
accent/form-insensitive fingerprints.

Executor commands
-----------------

``AC_simhash`` returns ``{simhash}`` for a ``text``; ``AC_near_duplicates``
returns ``{clusters}`` for ``texts`` within ``max_distance``. Both are exposed
as MCP tools (``ac_simhash`` / ``ac_near_duplicates``) and as Script Builder
commands under **Data**.
