Server-Sent Events(SSE)用戶端解析器
==================================

MCP 的 HTTP 傳輸會*發出* Server-Sent Events,但沒有任何東西消費它:一個串流 ``text/event-stream``
的 LLM、agent 或 chatops 端點,會讓 ``http_request`` 拿到未經解析的原始 blob。本功能實作 WHATWG
event-stream 解析演算法 —— ``event`` / ``data`` / ``id`` / ``retry`` 欄位、註解行、前導空白規則,以及
空白行派發 —— 並提供逐塊串流的增量 ``feed``。

純標準函式庫(``re``);不匯入 ``PySide6``。解析器為純函式且完全具決定性,因此串流邏輯可在無線上伺服器
的情況下於 CI 測試。

無頭 API
--------

.. code-block:: python

    from je_auto_control import parse_event_stream, SSEParser

    # 解析完整回應內文:
    for event in parse_event_stream(response_text):
        handle(event.event, event.data, event.id)

    # 或在資料塊抵達時逐塊解析:
    parser = SSEParser()
    for chunk in stream:
        for event in parser.feed(chunk):
            handle(event)
    for event in parser.close():           # 沖出尾端事件
        handle(event)

``SSEEvent`` 是派發出的 ``(event, data, id, retry)`` 組合(``event`` 預設 ``"message"``)。
``SSEParser.feed`` 在多次呼叫間緩衝尾端不完整的行,並回傳每個由空白行完成的事件;``close`` 會在串流
未以空白行結尾時沖出最後一個事件。``id`` 與 ``retry`` 依規範在後續事件間延續。``parse_event_stream``
是處理完整 blob 的一次性輔助函式,並會沖出尾端事件。

執行器命令
----------

``AC_parse_sse`` 把 ``text`` blob 解析成 ``{events}``(每筆 ``{event, data, id, retry}``)。它以 MCP
工具 ``ac_parse_sse`` 以及 Script Builder 中 **Data** 分類下的命令提供。
