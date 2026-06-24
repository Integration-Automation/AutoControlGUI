Visual Saliency (where to look — spectral-residual)
===================================================

When there is no template, no known colour and no text to OCR, an agent still
needs a cue for *where to look* — the region that stands out from its
surroundings (a popup, a badge, a highlighted row). ``saliency`` computes the
spectral-residual saliency map (Hou & Zhang 2007) — ``log`` amplitude minus its
local average, reconstructed through the phase — and turns it into ranked salient
boxes.

* :func:`saliency_map` — the normalised (0–1) saliency map as an ndarray,
* :func:`salient_regions` — ranked salient boxes ``{x, y, width, height, center,
  score}`` in source pixel coordinates,
* :func:`most_salient` — the single most salient region (the first place to look).

The transform is a pure ``numpy`` FFT — ``cv2.saliency`` lives in the forbidden
opencv-contrib package, so it is re-implemented over base opencv only. It reuses
``visual_match``'s grayscale loader (any ndarray / path / PIL image, or the live
screen) and ``cv2_utils.blobs.connected_boxes`` for region extraction. cv2 /
numpy are lazily imported. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import saliency_map, salient_regions, most_salient

    most_salient("screen.png")
    # {"x": 612, "y": 40, "width": 180, "height": 36, "center": [702, 58],
    #  "score": 0.82}

    for region in salient_regions("screen.png"):   # most-salient first
        ...

    sal = saliency_map("screen.png")               # (64, 64) float32 in 0..1

Regions are thresholded at ``mean + 2·std`` of the saliency map by default (pass
``threshold`` to override), extracted with ``connected_boxes`` and scaled back to
the source's pixel coordinates. ``size`` is the (small) resolution the saliency is
computed at. Saliency is a coarse attention cue, not a precise detector — use it
to *narrow* where a template / OCR pass then looks.

Executor commands
-----------------

``AC_salient_regions`` and ``AC_most_salient`` (``source`` / ``region`` / ``size``
/ ``threshold`` / ``min_area``). They are exposed as read-only ``ac_*`` MCP tools
and as Script Builder commands under **Image**.
