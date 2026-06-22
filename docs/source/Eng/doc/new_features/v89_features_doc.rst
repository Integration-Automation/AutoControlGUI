multipart/form-data Build & Parse
=================================

``http_request`` sends only JSON or raw bodies — there was no file upload, and
the stdlib ``cgi`` module (which once parsed multipart) was removed in Python
3.13. This assembles a ``multipart/form-data`` body from text fields and files
with a deterministic boundary, and parses one back.

Pure standard library (``re`` / ``secrets``); imports no ``PySide6``. The
boundary is injectable, so a built body is byte-stable and CI-testable.

Headless API
------------

.. code-block:: python

    from je_auto_control import build_multipart, parse_multipart, MultipartFile

    content_type, body = build_multipart(
        fields={"title": "Q3 report"},
        files=[MultipartFile("file", "report.csv", csv_text, "text/csv")],
    )
    http_request(url, method="POST",
                 headers={"Content-Type": content_type}, data=body)

    parsed = parse_multipart(content_type, body)   # {"fields": {...}, "files": [...]}

``build_multipart`` accepts ``fields`` (a dict or ``(name, value)`` list) and
``files`` (``MultipartFile`` instances or ``{name, filename, content,
content_type?}`` dicts), returning ``(content_type, body_bytes)``. Pass an
explicit ``boundary`` for a byte-stable body, or call ``new_boundary`` for a
fresh token. ``parse_multipart`` reads a body back into ``{fields, files}`` (each
file as ``{name, filename, content_type, content}``).

Executor commands
-----------------

``AC_build_multipart`` returns ``{content_type, body_base64}`` for ``fields`` /
``files`` (and an optional ``boundary``); ``AC_parse_multipart`` takes a
``content_type`` and ``body_base64`` and returns ``{fields, files}``. Both are
exposed as MCP tools (``ac_build_multipart`` / ``ac_parse_multipart``) and as
Script Builder commands under **Data**.
