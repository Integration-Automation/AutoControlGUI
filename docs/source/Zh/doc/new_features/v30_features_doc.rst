==================================================
新功能 (2026-06-19) — MCP 結構化工具輸出
==================================================

MCP 伺服器現在支援 2025-06-18 的**結構化工具輸出**規範:工具可宣告
``outputSchema``,其 dict 結果會在 ``tools/call`` 回應中以
``structuredContent`` 回傳(與一般的文字 ``content`` 並列)。MCP 用戶端
與 LLM 即可消費經 schema 驗證的型別化物件,而非重新解析文字——省 token、
少出錯。純標準庫;屬 MCP 框架增強(不新增 ``AC_*`` 指令)。

.. contents::
   :local:
   :depth: 2


宣告輸出 schema
===============

::

    from je_auto_control.utils.mcp_server.tools import MCPTool

    MCPTool(
        name="ac_validate_rows", description="...",
        input_schema=..., handler=validate_rows,
        output_schema={"type": "object", "properties": {
            "ok": {"type": "boolean"}, "errors": {"type": "array"}}},
    )

``to_descriptor()`` 會在 ``tools/list`` 中包含 ``outputSchema``;當
``tools/call`` 的 handler 回傳 ``dict`` 時,結果會包含 ``structuredContent``。
未宣告 ``outputSchema`` 的工具行為不變;非 dict 結果不會產生
``structuredContent``。

首個採用的內建工具是 ``ac_validate_rows``(資料品質驗證),其
``{ok, total, valid_count, invalid_count, errors, ...}`` 結果現在已型別化;
其他工具可透過加上 ``output_schema`` 逐步採用。
