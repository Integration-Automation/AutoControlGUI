OTLP/JSON Span 匯出
==================

``agent_trace.to_otel`` 回傳的是扁平 span dict,並非有效的 OTLP/JSON(沒有 ``resourceSpans`` /
``scopeSpans`` 巢狀、屬性未正確編碼、時間不是 uint64 字串)。本功能把一串 span 塑形成 OpenTelemetry
collector 可透過 file exporter 直接攝取的封套。

純標準函式庫(``json``);不匯入 ``PySide6``。時間由呼叫端提供(不使用 wall clock),因此封套位元組穩定、
可於 CI 測試。

無頭 API
--------

.. code-block:: python

    from je_auto_control import spans_to_otlp, write_otlp

    spans = [{
        "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
        "span_id": "00f067aa0ba902b7",
        "name": "run_suite",
        "start_unix_nano": started_ns, "end_unix_nano": ended_ns,
        "attributes": {"ok": True, "cases": 12},
    }]
    payload = spans_to_otlp(spans, resource_attrs={"service.name": "autocontrol"})
    write_otlp(payload, "trace.otlp.json")

``spans_to_otlp`` 把 span 包進 ``resourceSpans → scopeSpans → spans`` 結構:trace/span ID 維持 hex、
時間轉成 uint64 字串、屬性編碼為 OTLP ``KeyValue``(``stringValue`` / ``intValue`` / ``boolValue`` /
``doubleValue``)。``attributes_to_otlp`` 公開該屬性轉換,``write_otlp`` 把 payload 寫成 JSON。結果即為
OpenTelemetry collector file exporter 讀取的格式 —— 與 ``trace_context``(提供 ID)及 ``agent_trace``
(提供 span 資料)搭配。

執行器命令
----------

``AC_spans_to_otlp`` 把 ``spans``(以及選用的 ``resource_attrs``)包成 ``{payload}``。它以 MCP 工具
``ac_spans_to_otlp`` 以及 Script Builder 中 **Report** 分類下的命令提供。
