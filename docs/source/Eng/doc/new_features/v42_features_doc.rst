Perceptual-Hash Image Dedupe
============================

A screen recording or a step report often contains many nearly identical frames.
Perceptual hashes (average-hash and difference-hash) map visually similar images
to numerically close fingerprints, so frames can be clustered by Hamming distance
and collapsed — keeping one representative per distinct view.

The hashing functions use **Pillow** (already a core dependency — no extra
package required); the dedupe/compare logic is pure Python and the ``hasher`` is
injectable, so clustering is unit-testable without any image. Imports no
``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        average_hash, dhash, hamming_distance, images_similar, dedupe_images)

    h1 = average_hash("frame1.png")          # hex fingerprint
    h2 = average_hash("frame2.png")
    hamming_distance(h1, h2)                  # bits that differ
    images_similar(h1, h2, max_distance=5)   # within tolerance?

    dedupe_images(["a.png", "b.png", "c.png"], max_distance=5)
    # -> keeps one image per near-duplicate cluster (first wins)

``average_hash`` compares each pixel to the mean brightness; ``dhash`` compares
each pixel to its right neighbour (more robust to gamma shifts). ``dedupe_images``
accepts a ``hasher`` hook (defaulting to ``average_hash``) so the clustering can
be tested with precomputed hashes.

Executor commands
-----------------

================================ ===================================================
Command                          Effect
================================ ===================================================
``AC_image_hash``                ``{hash}`` of an image (``algo``: average/dhash).
``AC_dedupe_images``             ``{unique}`` with near-duplicate images collapsed.
================================ ===================================================

``paths`` accepts a list or a JSON-string list (so the visual builder works). The
same operations are exposed as MCP tools (``ac_image_hash`` / ``ac_dedupe_images``)
and as Script Builder commands under **Image**.
