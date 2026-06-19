Agent 可觀測性(GenAI OpenTelemetry Spans)
==========================================

當自動化驅動 LLM agent 時,你會想要 OpenTelemetry 後端給服務的那種可觀測性:每個操作
一個 span,帶有 token 用量、模型與狀態。``AgentTrace`` 記錄的 span 其屬性遵循
OpenTelemetry **GenAI 語意慣例** —— ``gen_ai.operation.name``、``gen_ai.system``、
``gen_ai.request.model``、``gen_ai.usage.input_tokens`` /
``gen_ai.usage.output_tokens``、``gen_ai.tool.name`` —— 以及慣例 span 名稱
``"{operation} {model}"``。:meth:`AgentTrace.to_otel` 的輸出可直接送入 OTLP
exporter,而 :meth:`AgentTrace.summary` 則彙整一次執行的成本與延遲。

它與 :doc:`軌跡評估 <v36_features_doc>` 互補 —— 在此記錄執行,在那裡評分。純標準函式
庫(無 ``opentelemetry`` 相依);時鐘可注入,因此持續時間可被確定性地測試。不匯入
``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import AgentTrace

    trace = AgentTrace()
    # 一次性記錄已完成的呼叫:
    trace.record("chat", model="claude-opus-4-8", system="anthropic",
                 input_tokens=1200, output_tokens=180, duration_s=0.9)

    # 或為即時區塊計時;在 yield 出的 dict 上設定 token 數:
    with trace.operation("tool", tool_name="search") as fields:
        result = run_tool()
        fields["output_tokens"] = 42        # 區塊內若拋出例外則標記為 error

    print(trace.summary())   # {span_count, error_count, input_tokens, ...}
    exporter.export(trace.to_otel())        # OTLP 友善的 span dict

``summary`` 彙整 ``span_count``、``error_count``、``input_tokens``、
``output_tokens`` 與總 ``duration_s``。``to_otel`` 將每個 span 回傳為
``{name, kind, attributes, duration_s, status:{code}}``,帶有 OTel 狀態碼。

執行器指令
----------

模組層級的預設 trace 支撐 executor/MCP 介面,讓流程可跨步驟建立一條 trace:

================================ ===================================================
指令                             效果
================================ ===================================================
``AC_trace_record``              記錄一個 GenAI span(operation/model/tokens/…)。
``AC_trace_summary``             彙整預設 trace。
``AC_trace_export``              將預設 trace 匯出為 OTLP spans。
``AC_trace_reset``               清除預設 trace。
================================ ===================================================

相同操作亦提供為 MCP 工具(``ac_trace_record`` / ``ac_trace_summary`` /
``ac_trace_export`` / ``ac_trace_reset``),以及 Script Builder 中 **Agent** 分類下的
指令。
