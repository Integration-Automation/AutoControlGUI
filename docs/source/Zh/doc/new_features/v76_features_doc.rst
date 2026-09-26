W3C Trace Context 傳播
=====================

``observability`` 追蹤器與 ``agent_trace`` 的 span 都不帶任何 ID,因此一次 HTTP 呼叫一端的 span
無法與它在另一端觸發的工作關聯起來。本功能加入 W3C Trace Context 標準 —— 產生、解析並傳播
``traceparent`` / ``tracestate`` 標頭,讓 span、日誌與下游服務共享同一條 trace 與 span 血緣。

純標準函式庫(``os`` / ``re``);不匯入 ``PySide6``。ID 產生可注入 RNG,因此 trace 與 span ID 在測試中
具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        new_root_context, child_context, inject_context, extract_context,
        parse_traceparent, format_traceparent,
    )

    # 開啟一條 trace 並傳播到外送請求:
    ctx = new_root_context()
    headers = inject_context({"accept": "application/json"}, ctx)
    # headers["traceparent"] == "00-<32 hex>-<16 hex>-01"

    # 接收端延續同一條 trace:
    parent = extract_context(request_headers)
    if parent is not None:
        span = child_context(parent)        # 相同 trace_id,新的 span_id

``SpanContext`` 是不可變的(``trace_id``、``span_id``、``trace_flags``、``tracestate``)組合。
``new_root_context`` 鑄造新 trace;``child_context`` 保留 trace id 與繼承狀態但配置新的 span id,並清掉 sampled 與 random
以外的旗標位元。
``parse_traceparent`` / ``format_traceparent`` 來回轉換 version-``00`` 標頭(較新的版本當作 ``00`` 讀取、忽略多出的欄位;
版本 ``ff``、格式不符或全零 ID 拋出 ``TraceContextError``,``format_traceparent`` 寫出前也會驗證手工建立的 context);
``parse_tracestate`` / ``format_tracestate`` 處理 vendor 清單。解析時只去掉逗號兩側的空格與 tab、保留值開頭的空格，捨棄鍵或值
不合文法的成員(空值、含 ``=`` 或 ``,``、超過 256 字元、控制字元),讀滿 32 個成員就停，鍵重複時回傳 ``[]``;格式化遇到這種成員會拋出
``TraceContextError``,不會寫出去。
``inject_context`` 寫入標頭;``extract_context`` 將其讀回(不分大小寫),``traceparent`` 缺少或無效時回傳
``None``,讓接收端依 W3C Trace Context 開一條新的 trace。

執行器命令
----------

``AC_trace_inject`` 把 context 傳播到外送 ``headers`` —— 帶 ``traceparent`` 時衍生該父節點的子 span,
否則開啟新的 root —— 回傳 ``{headers, traceparent, trace_id, span_id}``。``AC_trace_extract`` 從請求
``headers`` 讀回 context,回傳 ``{context}``(無 ``traceparent`` 時為 ``null``)。兩者皆以 MCP 工具
(``ac_trace_inject`` / ``ac_trace_extract``)以及 Script Builder 中 **Data** 分類下的命令提供。
