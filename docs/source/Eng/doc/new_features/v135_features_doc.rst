Image Pre-processing for OCR / Template Matching
================================================

``locate_text`` / ``ocr_read_structure`` and ``match_template`` feed the *raw*
screen capture straight to the OCR engine or the matcher. Small UI text, dark
themes, low contrast and a slightly rotated screenshot wreck both — and there was
no preprocessing seam anywhere in the framework. This adds the standard pre-step
pipeline — grayscale → upscale → binarize → deskew → denoise → CLAHE contrast —
that multiplies the accuracy of the OCR and matching features you already use.

Every function runs on an injectable ``haystack`` image (ndarray / path / PIL,
default: grab the screen / ``region``) and returns a NumPy ndarray, so it is
unit-testable on synthetic arrays. OpenCV + NumPy come in via ``je_open_cv``.
Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import preprocess_image, binarize, deskew, upscale

    # One-shot pipeline, then OCR the cleaned image.
    clean = preprocess_image("receipt.png", steps=("grayscale", "upscale",
                                                    "deskew", "binarize"), scale=2.0)

    # Or compose the individual steps.
    bw = binarize("panel.png", method="adaptive_gaussian", block_size=41)
    straight = deskew("scan.png", max_angle=10.0)
    big = upscale("tiny_label.png", scale=3.0, interp="lanczos")

The building blocks are ``to_grayscale``, ``upscale`` (``scale`` / ``interp``),
``binarize`` (``method`` = ``otsu`` / ``adaptive_mean`` / ``adaptive_gaussian``),
``denoise``, ``enhance_contrast`` (CLAHE), ``deskew`` and ``detect_skew_angle``
(returns the measured text-skew in degrees, clamped to ``±max_angle``).
``preprocess_image`` chains any of the named ``steps`` — ``grayscale``,
``upscale``, ``binarize``, ``denoise``, ``deskew``, ``contrast`` — in order;
unknown step names raise ``ValueError``.

Executor command
----------------

``AC_preprocess_image`` runs the pipeline and *writes* the result to
``output_path`` (so it is usable from JSON / MCP / the builder): ``source`` is an
image path (default: screen grab of ``region``), ``steps`` an ordered list (or
comma string), plus ``scale`` / ``block_size`` / ``c``; it returns
``{path, width, height}``. It is exposed as the MCP tool ``ac_preprocess_image``
and as a Script Builder command under **Image**.
