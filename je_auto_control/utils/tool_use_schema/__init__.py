"""Phase 7.8: export AC_* commands as Claude / OpenAI tool-use schemas.

Both Anthropic's tool-use and OpenAI's function-calling expect a JSON
schema describing each tool's name, description, and parameters. This
module walks the executor's dispatch table, introspects every
``AC_*`` command's signature, and emits the schema in either dialect.

Typical use::

    from je_auto_control.utils.tool_use_schema import (
        export_anthropic_tools, export_openai_tools,
    )

    tools = export_anthropic_tools()
    response = anthropic.messages.create(
        model="claude-opus-4-7", tools=tools, ...
    )

When the model asks for ``tool_use``, hand the call's ``name`` and
``input`` to :func:`run_tool_call` — it dispatches through the same
executor that JSON action files use, so model-driven and operator-
driven flows share one implementation.
"""
from je_auto_control.utils.tool_use_schema.schema import (
    export_anthropic_tools, export_openai_tools, infer_parameters,
    run_tool_call,
)

__all__ = [
    "export_anthropic_tools", "export_openai_tools",
    "infer_parameters", "run_tool_call",
]
