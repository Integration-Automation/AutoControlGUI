W3C Baggage 傳播
===============

``trace_context`` 能跨 HTTP 邊界攜帶 trace 與 span 身分,但沒有辦法在旁邊一併傳播橫切的鍵值脈絡
(``run_id`` / ``tenant`` / ``experiment``)。本功能實作 W3C Baggage 標頭 —— 一個 percent-encoded 的
``key=value`` 清單 —— 讓一次執行能把這類脈絡附加到外送請求,並在另一端讀回。

純標準函式庫(``urllib.parse``);不匯入 ``PySide6``。``Baggage`` 不可變(變更操作回傳新實例),因此
傳播具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import Baggage, inject_baggage, extract_baggage

    bag = Baggage({"tenant": "acme"}).set("run_id", "42")
    headers = inject_baggage(outgoing_headers, bag)
    # headers["baggage"] == "tenant=acme,run_id=42"

    received = extract_baggage(request_headers)
    tenant = received.get("tenant")

``Baggage`` 包裝一個不可變的鍵值對應:``get`` 讀取,``set`` / ``remove`` 回傳新實例,``to_dict`` 匯出
條目。``parse_baggage`` 解析標頭(去除選用的 ``;metadata`` 並拒絕空鍵),``format_baggage`` 將鍵與值
percent-encode 回標頭值,``inject_baggage`` / ``extract_baggage`` 在請求 dict 上寫入與讀取 ``baggage``
標頭(讀取不分大小寫)。與 ``trace_context`` 自然搭配,在 trace 之外攜帶脈絡。

執行器命令
----------

``AC_baggage_parse`` 把 ``header`` 解析成 ``{items}``;``AC_baggage_format`` 把 ``items`` 物件序列化成
``{header}``。兩者皆以 MCP 工具(``ac_baggage_parse`` / ``ac_baggage_format``)以及 Script Builder 中
**Data** 分類下的命令提供。
