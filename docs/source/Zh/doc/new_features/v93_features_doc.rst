標準日誌行與結構化日誌
====================

``logging_instance`` 輸出固定的管線分隔人類字串,沒有 JSON 選項也沒有 trace/span 欄位,但 OTel 的
log-trace 關聯需要每筆記錄都帶 ``trace_id`` / ``span_id``。本功能加入 Stripe 風格的標準日誌行(每次執行
輸出一個寬欄位包)以及一個攜帶 trace 脈絡的 JSON ``logging.Formatter``。

純標準函式庫(``json`` / ``logging``);不匯入 ``PySide6``。計時器時鐘可注入,因此時長在 CI 中具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        CanonicalLogLine, bind_trace_context, JSONLogFormatter,
        new_root_context,
    )

    line = CanonicalLogLine({"event": "run_suite"})
    bind_trace_context(line, new_root_context())
    with line.timer("execute"):
        run()
    line.add("ok", True).emit(logger.info)         # 每次執行一行寬事件

    # 帶 trace 關聯的結構化日誌:
    handler.setFormatter(JSONLogFormatter())

``CanonicalLogLine`` 累積請求範圍的欄位(``add`` / ``update``),透過 ``timer``(可注入時鐘)把一段區塊
計入 ``{name}_ms``,並以 ``render`` / ``emit`` 將寬事件行輸出為 JSON。``bind_trace_context`` 附上
``SpanContext`` 的 ``trace_id`` / ``span_id``。``JSONLogFormatter`` 是一個 ``logging.Formatter``,每筆記錄
輸出一個 JSON 物件,包含 ``trace_id`` / ``span_id`` 與任何 ``extra=`` 欄位 —— 與 ``trace_context`` 對應的
log-trace 關聯。

執行器命令
----------

``AC_canonical_log`` 從 ``fields`` 物件建立標準日誌行,回傳 ``{line, json}``。它以 MCP 工具
``ac_canonical_log`` 以及 Script Builder 中 **Report** 分類下的命令提供。
