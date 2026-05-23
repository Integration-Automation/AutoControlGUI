================================
OCR backends
================================

AutoControl ships three pluggable OCR engines behind a unified API. Pick
the one that fits your install constraints and your script's languages:

================  ==================================================  ====================================
Backend           Best for                                            Install
================  ==================================================  ====================================
``tesseract``     ASCII / Western languages, lightest dependency      ``pip install pytesseract`` + ``tesseract.exe`` on PATH
``easyocr``       CJK without an external binary, simplest install    ``pip install easyocr`` (downloads ~64 MB model on first use)
``paddleocr``     Highest-quality Chinese / Japanese / Korean         ``pip install paddlepaddle paddleocr``
================  ==================================================  ====================================

Backend selection
=================

The active backend is chosen in this order:

1. The ``backend=`` keyword argument on a public OCR call.
2. The ``AUTOCONTROL_OCR_BACKEND`` environment variable.
3. Auto-detection — tries ``tesseract`` → ``easyocr`` → ``paddleocr`` and
   uses the first one that imports successfully.

So in practice, you ``pip install`` exactly the backend you want and let
auto-detection wire the rest::

   from je_auto_control import find_text_matches

   # No backend kwarg, no env var → auto-detect.
   matches = find_text_matches("Sign in")

To force a specific backend::

   matches = find_text_matches("Sign in", backend="easyocr")

Or process-wide::

   $ AUTOCONTROL_OCR_BACKEND=paddleocr python my_script.py

Language codes
==============

Each backend exposes its own native language codes, but the public API
accepts a single canonical form and translates at the edge. Pass
Tesseract-style codes — every backend understands them:

==========================  ==================  ==================  ==================
AutoControl canonical lang  Tesseract           EasyOCR             PaddleOCR
==========================  ==================  ==================  ==================
``eng``                     ``eng``             ``en``              ``en``
``chi_tra`` / ``zh-TW``     ``chi_tra``         ``ch_tra``          ``chinese_cht``
``chi_sim`` / ``zh-CN``     ``chi_sim``         ``ch_sim``          ``ch``
``jpn``                     ``jpn``             ``ja``              ``japan``
``kor``                     ``kor``             ``ko``              ``korean``
==========================  ==================  ==================  ==================

For other languages (fra, ger, ara, etc.) pass the backend's own code and
it goes through unchanged.

Tesseract setup notes
=====================

Windows users need to install the Tesseract binary separately (UB-Mannheim
build is the most common). If ``tesseract.exe`` is not on ``PATH``::

   from je_auto_control import set_tesseract_cmd
   set_tesseract_cmd(r"C:\Program Files\Tesseract-OCR\tesseract.exe")

Language pack files (``*.traineddata``) live under
``Tesseract-OCR\\tessdata\\`` — copy the ones you need from the
`tessdata GitHub repo <https://github.com/tesseract-ocr/tessdata>`_.

EasyOCR / PaddleOCR setup notes
================================

Both engines lazy-download neural models on the first call for a given
language. The model files end up in:

- EasyOCR: ``~/.EasyOCR/model/`` (~64 MB per language).
- PaddleOCR: ``~/.paddleocr/`` (~50 MB combined detector + recognizer).

The first call is therefore much slower than subsequent calls — wrap it
in your test setup or pre-warm at boot.

Headless usage
==============

All three backends honour AutoControl's "feature must work without the
GUI" rule. The full public surface::

   from je_auto_control import (
       find_text_matches, locate_text_center, wait_for_text,
       click_text, read_text_in_region, find_text_regex,
   )

Each function takes the same arguments (``lang``, ``region``,
``min_confidence``, ``backend``, ``case_sensitive``) and returns
``TextMatch`` records with absolute screen coordinates already applied.

JSON action surface
===================

OCR commands are exposed through the executor for JSON action files::

   {"command": "AC_locate_text", "text": "Sign in", "lang": "eng"}
   {"command": "AC_click_text",  "text": "OK",      "backend": "easyocr"}

Both commands accept the same arguments as their Python counterparts.

Diagnostics
===========

To check which backends are reachable in the current environment::

   from je_auto_control.utils.ocr.backends import get_backend

   for name in ("tesseract", "easyocr", "paddleocr"):
       try:
           backend = get_backend(name)
           print(name, "ok" if backend.available else "not available")
       except Exception as exc:  # noqa: BLE001
           print(name, "broken:", exc)
