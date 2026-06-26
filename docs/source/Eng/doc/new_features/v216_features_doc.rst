Sample a Region's Text Contrast (WCAG)
======================================

:func:`a11y_audit.contrast_ratio` grades a foreground / background pair you
already know. But when you only have a *region* of the screen — a button, a
label — you don't know those two colours; you have a patch of pixels.
``contrast_map`` closes that gap: split a sampled region into its dominant
foreground (the minority — usually the text) and background (the majority)
colours, then grade their WCAG contrast.

* :func:`grade_contrast` — pure: a foreground / background pair to
  ``{ratio, aa, aaa, aa_large, aaa_large}`` against the WCAG 2.x thresholds.
* :func:`dominant_pair` — pure: split a list of sampled RGB pixels into the
  dominant ``{foreground, background}`` colours by luminance.
* :func:`region_contrast` — sample a screen region and grade it, through an
  injectable ``sampler`` (the real screen grab by default).

The grading and split are pure and reuse :func:`a11y_audit.contrast_ratio`, so
they are fully testable without a screen. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import grade_contrast, dominant_pair, region_contrast

    # If you already know the colours:
    grade_contrast((90, 90, 90), (255, 255, 255))
    # {'ratio': 3.9, 'aa': False, 'aaa': False, 'aa_large': True, ...}

    # If you only have a region of the screen, sample and grade it:
    report = region_contrast(region=[x, y, w, h])
    if not report["aa"]:
        print("low-contrast text", report["foreground"], report["background"])

``dominant_pair`` partitions the sampled pixels at the mean luminance and treats
the larger group as the background and the smaller as the text — a uniform patch
yields the same colour for both (no contrast). ``region_contrast`` accepts an
injectable ``sampler`` (``region -> list of RGB pixels``) so the logic is tested
without a real screen.

Executor commands
-----------------

``AC_grade_contrast`` (``foreground`` / ``background`` ``[r, g, b]`` → the
grade), ``AC_dominant_pair`` (``pixels`` JSON list of ``[r, g, b]`` →
``{foreground, background}``) and ``AC_region_contrast`` (``region``
``[x, y, w, h]`` → the grade + colours + ``samples``). They are the matching
read-only ``ac_*`` MCP tools and Script Builder commands under **Image**.
