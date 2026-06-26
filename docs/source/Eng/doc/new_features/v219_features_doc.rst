Classify a Widget from Its Pixel Shape
======================================

Set-of-Marks and element proposers hand back *boxes*, but not *what each box is*.
``form_fields.checkbox_state`` already reads a box known to be a checkbox; the
gap is the typing step before it — is this box a checkbox, a radio button, a push
button, a text field or a toggle? ``icon_classify`` answers that from cheap
geometric features (no model).

* :func:`box_features` — extract ``{aspect, fill, edge_density, circularity}``
  for a box region (the objective measurements).
* :func:`classify_widget` — pure: map a feature dict to a widget type by
  documented heuristics.
* :func:`classify_icon` — compose the two: a box to ``{type, features}``.

``classify_widget`` is pure and fully testable; ``box_features`` imports cv2 /
numpy lazily (the module stays importable without them) and reuses
:func:`visual_match._to_gray`. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import classify_icon, classify_widget

    # From a screenshot + a box:
    classify_icon("dialog.png", [120, 80, 16, 16])
    # {'type': 'checkbox', 'features': {'aspect': 1.0, 'fill': 0.12, ...}}

    # From features you already have:
    classify_widget({"aspect": 1.0, "circularity": 0.9, "fill": 0.4})  # 'radio'

The heuristics: a round box (aspect ≈ 1, high circularity) is a ``radio``; a wide
rounded box is a ``toggle``; a near-square sparse box is a ``checkbox``; a wide
hollow box is a ``text_field``; a wide filled box is a ``button``; anything else
is an ``icon``. Tune by reading ``features`` and applying your own rules where
the defaults misfire — the measurements are the durable part.

Executor commands
-----------------

``AC_classify_widget`` (``features`` JSON object → ``{type}``, pure) and
``AC_classify_icon`` (``source`` image + ``box`` ``[x, y, w, h]`` →
``{type, features}``). They are the matching read-only ``ac_*`` MCP tools and
Script Builder commands under **Image**.
