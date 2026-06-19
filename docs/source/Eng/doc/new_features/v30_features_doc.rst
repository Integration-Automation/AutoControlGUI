==================================================
New Features (2026-06-19) — MCP Structured Tool Output
==================================================

The MCP server now supports the 2025-06-18 **structured tool output** spec
feature: a tool may declare an ``outputSchema``, and its dict result is
returned as ``structuredContent`` in the ``tools/call`` response (alongside
the usual text ``content``). MCP clients and LLMs can then consume a typed,
schema-validated object instead of re-parsing text — saving tokens and
errors. Pure standard library; an MCP-framework enhancement (no new
``AC_*`` command).

.. contents::
   :local:
   :depth: 2


Declaring an output schema
=========================

::

    from je_auto_control.utils.mcp_server.tools import MCPTool

    MCPTool(
        name="ac_validate_rows", description="...",
        input_schema=..., handler=validate_rows,
        output_schema={"type": "object", "properties": {
            "ok": {"type": "boolean"}, "errors": {"type": "array"}}},
    )

``to_descriptor()`` then includes ``outputSchema`` in ``tools/list``, and a
``tools/call`` whose handler returns a ``dict`` includes
``structuredContent`` in the result. Tools without an ``outputSchema`` are
unchanged; non-dict results never produce ``structuredContent``.

The first built-in tool to adopt this is ``ac_validate_rows`` (data-quality
validation), whose ``{ok, total, valid_count, invalid_count, errors, ...}``
result is now schema-typed; more tools can opt in by adding an
``output_schema``.
