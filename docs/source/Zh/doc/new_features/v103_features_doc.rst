冪等鍵儲存
========

``resilience.RetryPolicy`` 在重試時*重新執行*,``work_queue`` 只對進行中的參照去重 —— 沒有東西快取
第一次的結果,讓重複請求能回傳*相同*回應而不重跑副作用。這是 Stripe 的冪等模式:註冊一個鍵、把工作
執行一次,並為任何重複請求重播已儲存的回應。

純標準函式庫(``hashlib`` / ``json``);不匯入 ``PySide6``。時鐘可注入,儲存為記憶體內並具 JSON 持久化,
因此 TTL 過期與重播在 CI 中完全具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import IdempotencyStore, request_fingerprint

    store = IdempotencyStore(ttl=86400)
    state = store.begin("order-42", request_fingerprint(payload))
    if state["status"] == "completed":
        return state["response"]            # 重播 —— 不要重跑
    result = charge(payload)                 # 副作用只執行一次
    store.complete("order-42", result)

``begin`` 回傳 ``{status, response}``,status 為 ``new``(首次)、``in_progress``(完成前的重複)或
``completed``(重播已儲存回應);以不同 ``request`` 指紋重用同一鍵會拋出 ``IdempotencyConflict``
(Stripe 的 HTTP-400 行為)。``complete`` 記錄回應,``get`` 讀取有效記錄,``save`` / ``load`` 以 JSON
持久化。``request_fingerprint`` 是 payload 的穩定、與順序無關的 SHA-256。

執行器命令
----------

``AC_idempotency_begin`` 在具名儲存中註冊/查找 ``key``(可選 ``request`` 做衝突偵測);
``AC_idempotency_complete`` 儲存 ``response``。兩者使用具名實例登錄(如斷路器/隔艙),並以 MCP 工具
(``ac_idempotency_begin`` / ``ac_idempotency_complete``)以及 Script Builder 中 **Flow** 分類下的命令提供。
