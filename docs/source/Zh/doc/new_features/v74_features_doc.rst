隔艙與速率限制標頭
=================

``resilience`` 從失敗中復原,``rate_limit`` 為呼叫調速,但沒有任何東西能限制對單一資源*同時*進行
的呼叫數(因此一個緩慢的相依會耗盡所有 worker),而 HTTP 用戶端會讀取 ``Retry-After`` /
``RateLimit-*`` 回應標頭卻不予理會。本功能補上一個隔艙(bounded-concurrency 許可,含負載卸除)
以及一個解析伺服器建議延遲的剖析器。

純標準函式庫(``threading`` + ``email.utils``);許可計數為非阻塞(滿載即拒絕),因此具決定性、
不需開執行緒即可在 CI 測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import Bulkhead, BulkheadFullError, next_delay

    payments = Bulkhead(max_concurrent=4, name="payments")
    try:
        result = payments.run(call_payment_api, order)
    except BulkheadFullError:
        defer(order)               # 卸除負載而非繼續堆積

    # HTTP 呼叫後遵守伺服器的退避
    wait = next_delay(response)     # 來自 Retry-After / RateLimit-* 標頭
    if wait:
        sleep(wait)

``Bulkhead`` 把同時持有者上限設為 ``max_concurrent`` —— ``try_enter`` / ``release``、context
manager 與 ``run(func)`` 在滿載時皆拒絕(``BulkheadFullError``),把一個緩慢相依與其餘隔離。
``parse_retry_after`` 同時理解 delta 秒數與 HTTP-date 兩種形式;``parse_ratelimit`` 讀取
``RateLimit-Limit/Remaining/Reset`` 慣例;``next_delay`` 把它們結合成流程在 ``429`` / ``503`` 後
應遵守的等待。

執行器命令
----------

``AC_bulkhead_run`` 在具名隔艙(``name``、``max_concurrent``)下執行 ``actions`` 清單,回傳
``{entered, in_flight, record?}``。``AC_retry_after`` 接受 HTTP ``response``(``{status, headers}``)
回傳 ``{delay}``。兩者皆以 MCP 工具(``ac_bulkhead_run`` / ``ac_retry_after``)以及 Script Builder
中 **Flow** 分類下的命令提供。
