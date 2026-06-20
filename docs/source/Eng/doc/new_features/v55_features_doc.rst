Text PII Detection & Redaction
==============================

The image-redaction module blurs PII in screenshots, but text scraped from a UI,
OCR, the clipboard, an LLM prompt/response, or a log line had no string-level
equivalent — so PII could leak into action records, audit logs, or a model call.
``detect_pii`` / ``redact_pii_text`` find and mask emails, phone numbers, SSNs,
credit-card numbers, IPv4 addresses, and IBANs over plain text.

Patterns are deliberately simple (no nested quantifiers → no catastrophic
backtracking). Pure standard library (``re`` + ``hashlib``); imports no
``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import detect_pii, redact_pii_text

    detect_pii("mail a@b.com, ip 10.0.0.1")
    # -> [PIIFinding(kind='email', value='a@b.com', start=5, end=12), ...]

    redact_pii_text("contact a@b.com")                    # -> "contact [email]"
    redact_pii_text("a@b.com", mode="mask")               # -> "*******"
    redact_pii_text("4111111111111111", mode="partial")   # -> "************1111"
    redact_pii_text("a@b.com", mode="hash")               # -> "[email:fb98d44a]"

    detect_pii(text, kinds=["email", "phone"])            # restrict detectors

``detect_pii`` returns non-overlapping findings sorted by position (the earlier,
then longer, match wins — so a credit-card number is not also flagged as a
phone). ``redact_pii_text`` modes: ``label`` (``[email]``), ``mask`` (``****``),
``partial`` (keep last 4), ``hash`` (``[email:<digest>]``).

Executor commands
-----------------

================================ ===================================================
Command                          Effect
================================ ===================================================
``AC_detect_pii``                ``{findings}`` — PII spans in text.
``AC_redact_pii``                ``{text}`` — text with PII masked.
================================ ===================================================

``kinds`` accepts a list or JSON-string list. The same operations are exposed as
MCP tools (``ac_detect_pii`` / ``ac_redact_pii``) and as Script Builder commands
under **Data**.
