JSON Pointer, Patch & Merge Patch
=================================

``jsonpath`` queries are read-only and ``approval`` compares whole artifacts by
equality, but nothing could address a single location, compute a structured
*delta*, or apply a partial update to a JSON document. This adds the three IETF
primitives that fill that gap:

* **RFC 6901 JSON Pointer** — address one location (``/a/b/0``).
* **RFC 6902 JSON Patch** — an ordered op list
  (add/remove/replace/move/copy/test); plus ``make_patch`` to diff two docs.
* **RFC 7386 JSON Merge Patch** — a recursive merge where ``null`` deletes.

Useful for config-drift detection, partial updates in flows, HTTP PATCH bodies,
and reporting golden-master deltas. Pure standard library (``json`` + ``copy``);
fully deterministic; imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import (
        resolve_pointer, make_patch, apply_patch, merge_patch,
        make_merge_patch, set_pointer, remove_pointer)

    doc = {"user": {"name": "Jo", "tags": ["a", "b"]}}

    resolve_pointer(doc, "/user/tags/0")          # "a"

    patch = make_patch(doc, {"user": {"name": "Joe", "tags": ["a"]}})
    # [{"op": "replace", "path": "/user/name", "value": "Joe"},
    #  {"op": "remove",  "path": "/user/tags/1"}]
    apply_patch(doc, patch)                        # the updated document

    merge_patch({"a": 1, "b": 2}, {"b": None, "c": 3})   # {"a": 1, "c": 3}

``apply_patch`` is **atomic** — it applies to a copy and only returns on full
success, so a failing ``test`` op leaves the original untouched. The six ops
follow RFC 6902 exactly (``add`` inserts into arrays, ``test`` does deep
equality keeping ``true`` distinct from ``1``, ``move`` rejects moving a value
into its own child). ``set_pointer`` / ``remove_pointer`` are pure
single-location convenience helpers. ``merge_patch`` follows RFC 7386 (a
``null`` value deletes the key; a non-object patch replaces wholesale).

Executor commands
-----------------

``AC_resolve_pointer`` (``{value}``), ``AC_apply_json_patch`` (``{result}``),
``AC_make_json_patch`` (``{patch}``) and ``AC_merge_patch`` (``{result}``) take
their JSON inputs as objects or JSON strings. Each is also exposed as an MCP
tool (``ac_resolve_pointer`` / ``ac_apply_json_patch`` / ``ac_make_json_patch``
/ ``ac_merge_patch``) and as a Script Builder command under **Data**.
