Barcode Decoding (1-D)
======================

The framework already decodes QR codes (``read_qr``), but had no reader for the
*1-D* barcodes (EAN-13 / EAN-8 / UPC-A / Code-128) that label physical goods,
inventory tickets and shipping labels — the most common thing a desktop or kiosk
automation needs to read off a product screen. ``read_barcodes`` fills that gap
using OpenCV's ``cv2.barcode.BarcodeDetector``.

The decode step is an **injectable seam**: the default decoder calls OpenCV, but
tests (and alternative engines) can pass their own ``decoder`` callable, so the
feature is fully unit-testable headlessly and degrades gracefully — a build of
OpenCV without the ``barcode`` module simply returns an empty list instead of
raising. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import read_barcodes

    # decode every 1-D barcode currently on screen
    for code in read_barcodes():
        print(code["type"], code["text"], code["points"])

    # restrict to a region, or decode a saved image instead of the screen
    read_barcodes(region=[0, 0, 400, 200])
    read_barcodes("label.png")

``read_barcodes(source=None, *, region=None, decoder=None)`` returns a list of
``{"text", "type", "points"}`` dicts, one per detected barcode (``points`` is the
four-corner polygon in image coordinates). ``source`` may be an image path or an
array; when omitted the screen (optionally cropped to ``region``) is grabbed. The
grayscale conversion reuses the shared ``visual_match`` haystack loader, so no new
image-loading code is added.

Executor command
----------------

``AC_read_barcodes`` (``source`` / ``region`` → ``{count, barcodes}``) is exposed
as the MCP tool ``ac_read_barcodes`` (read-only) and as a Script Builder command
**Read Barcodes (1-D)** under **OCR**.
