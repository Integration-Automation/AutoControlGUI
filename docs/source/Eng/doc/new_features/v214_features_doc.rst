Colour-Vision-Deficiency Simulation + Collision Check
=====================================================

Status UIs lean on colour — a green "ok" vs a red "error" dot, a colour-coded
chart legend. For the ~8% of men with a colour-vision deficiency (CVD) those can
be indistinguishable, and nothing in the framework could check it.
``cvd_simulate`` adds the two primitives an accessibility / design check needs.

* :func:`simulate_cvd` — map an ``(r, g, b)`` colour through a dichromat
  simulation matrix (``protanopia`` / ``deuteranopia`` / ``tritanopia``) at a
  given ``severity`` (0 = unaffected, 1 = full dichromacy).
* :func:`colors_collide` — simulate two colours under a CVD type and report
  whether they become too similar to tell apart (a perceptual ``redmean``
  distance below ``threshold``).
* :func:`color_distance` — the underlying ``redmean`` colour-difference metric.

Pure standard library — no numpy / OpenCV — operating on plain RGB tuples, so it
is fully testable. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import simulate_cvd, colors_collide

    # How does the "error red" look to a deuteranope?
    simulate_cvd((220, 40, 40), "deuteranopia")        # -> (r, g, b)

    # Are my ok-green and error-red distinguishable for them?
    report = colors_collide((60, 200, 60), (220, 60, 60), kind="deuteranopia")
    report["collide"]    # True if the two are confusable
    report["distance"]   # the perceptual distance after simulation

``simulate_cvd`` accepts friendly aliases (``protan`` / ``deutan`` / ``tritan``,
or ``red`` / ``green`` / ``blue``). ``severity`` interpolates between the
original colour and the full dichromat simulation, for the milder anomalous
trichromacies. ``colors_collide`` returns ``{collide, distance, kind, severity,
simulated_left, simulated_right}``.

Executor commands
-----------------

``AC_simulate_cvd`` (``rgb`` ``[r, g, b]`` + ``kind`` / ``severity`` →
``{rgb}``) and ``AC_colors_collide`` (``left`` / ``right`` ``[r, g, b]`` +
``kind`` / ``severity`` / ``threshold`` → the report). RGB inputs accept a JSON
list. They are the matching read-only ``ac_*`` MCP tools and Script Builder
commands under **Image**.
