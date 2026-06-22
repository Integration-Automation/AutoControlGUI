==================================================
New Features (2026-06-19) — Data Quality
==================================================

Three pure-standard-library data-quality helpers from the data/validation
research angle — the quality gate between ingestion (``load_rows`` / OCR)
and downstream entry. Wired through the full stack (facade, ``AC_*``
executor commands, MCP tools, Script Builder).

.. contents::
   :local:
   :depth: 2


Row schema validation
====================

Validate scraped / loaded rows against a declarative schema before they
reach an ERP or form — bad data caught here doesn't corrupt downstream::

    from je_auto_control import validate_rows

    report = validate_rows(rows, {
        "name": {"type": "str", "required": True},
        "age": {"type": "int", "min": 0, "max": 130},
        "email": {"regex": r".+@.+\..+"},
        "id": {"unique": True},
        "tier": {"allowed": ["gold", "silver"]},
    })
    report["ok"]          # False if any row failed
    report["valid"]       # rows that passed
    report["errors"]      # [{"row": 1, "field": "age", "error": "above max 130"}]

Rules: ``type`` / ``required`` / ``regex`` / ``min`` / ``max`` /
``min_len`` / ``max_len`` / ``allowed`` / ``unique``. Exposed as
``AC_validate_rows`` / ``ac_validate_rows``.


Field extraction
===============

Pull structured values out of free text / OCR blobs with named regex
presets (plus your own ``patterns``)::

    from je_auto_control import extract_fields

    out = extract_fields("Mail ada@x.io on 2026-06-19",
                         fields=["email", "date_iso"])
    # {"email": ["ada@x.io"], "date_iso": ["2026-06-19"]}

Presets: ``email`` / ``url`` / ``ipv4`` / ``phone`` / ``date_iso`` /
``amount`` / ``hashtag``. Exposed as ``AC_extract_fields`` /
``ac_extract_fields``.


Row masking
==========

Mask sensitive columns before exporting rows / reports (the existing
redaction is screenshot-only)::

    from je_auto_control import mask_rows

    safe = mask_rows(rows, {"ssn": "partial", "token": "redact",
                            "name": "hash"})
    # ssn -> "*****6789", token -> "***", name -> sha256 hex

Modes: ``redact`` (``***``), ``hash`` (SHA-256 hex), ``partial`` (keep the
last 4 chars). Exposed as ``AC_mask_rows`` / ``ac_mask_rows``.
