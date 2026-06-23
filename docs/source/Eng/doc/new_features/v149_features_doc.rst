Perceptual (YIQ) Image Diff with Anti-Alias Suppression
=======================================================

``visual_regression.image_difference`` counts raw per-channel max-delta pixels and
``ssim_compare`` gives a global structural score. Neither uses a *perceptual* colour
metric, and neither ignores **anti-aliased edges** — the #1 source of false-positive
visual-diff failures across DPI and font-hinting. ``perceptual_diff`` compares pixels
in YIQ space (the pixelmatch colour metric, far closer to human perception than RGB)
and, by default, removes the thin one-pixel edge differences that anti-aliasing
produces (a morphological open), so only *solid* changed regions count.

Runs on an injectable image pair (ndarray / path / PIL), so it is headless-testable on
synthetic arrays. OpenCV + NumPy come in via ``je_open_cv``; reuses the shared
connected-component helper and RGB loader. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import perceptual_diff, assert_perceptual

    result = perceptual_diff("actual.png", "golden.png", threshold=0.1)
    print(result.diff_pixels, result.diff_ratio, result.regions)

    # Gate a visual-regression test (raises if the ratio is exceeded).
    assert_perceptual("actual.png", "golden.png", max_diff_ratio=0.01)

``perceptual_diff`` returns a ``PerceptualDiffResult`` (``diff_pixels``,
``total_pixels``, ``diff_ratio``, and the ``regions`` boxes of the changed clusters).
``threshold`` (0..1) is the pixelmatch sensitivity. ``include_aa=True`` keeps the thin
edge differences instead of suppressing them. ``assert_perceptual`` raises
``AutoControlActionException`` when ``diff_ratio`` exceeds ``max_diff_ratio``. Images of
different sizes raise ``ValueError``.

Executor command
----------------

``AC_perceptual_diff`` (``actual`` / ``expected`` / ``threshold`` / ``include_aa`` /
``max_diff_ratio`` → ``{diff_pixels, total_pixels, diff_ratio, regions}``; raises when
``max_diff_ratio`` is given and exceeded). It is exposed as the MCP tool
``ac_perceptual_diff`` and as a Script Builder command under **Image**.
