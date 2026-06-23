變化量序列的穩定偵測
====================

``smart_waits.wait_until_screen_stable`` 與 ``actionability`` 的穩定檢查把穩定邏輯包在
``time.sleep`` 輪詢迴圈內、作用於即時像素幀——你無法餵給它一段記錄好的 a11y 元素數或畫面
差異指標序列,也無法獨立於擷取去單元測試那個*決策*。``settle_detector`` 把該決策抽離:它接收
一串*變化量*(churn,每個樣本變了多少——像素差、元素數差、digest 是否變的 0/1,皆可),並在
變化量連續 ``quiet_samples`` 次維持在 ``max_churn`` 以下時回報穩定。尖峰會重置 quiet run,因此
「穩定後又變動」也能處理。

純標準函式庫;確定性、可在注入序列上單元測試,不需擷取、不需時鐘。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import settle_point, is_settled, SettleTracker

    churns = [5, 4, 0.5, 0.3, 0.2]          # 每幀變化量指標
    settle_point(churns, quiet_samples=3, max_churn=1.0)   # -> 4
    is_settled(churns, quiet_samples=3, max_churn=1.0)     # -> True

    # 增量版,供即時迴圈(你每 tick 提供 churn)
    tracker = SettleTracker(quiet_samples=3, max_churn=1.0)
    state = tracker.update(current_churn)
    if state.settled:
        observe_now()

``settle_point`` 回傳序列首次穩定的索引(或 ``None``);``is_settled`` 為布林。``SettleTracker``
為增量形式:``update(churn)`` 回傳 ``SettleState``(``settled`` / ``quiet_run`` / ``churn``);
``reset`` 清除 run(例如在再次動作後)。

執行器指令
----------

``AC_settle_point``(``churns`` / ``quiet_samples`` / ``max_churn`` → ``{settled, index}``)
以 MCP 工具 ``ac_settle_point``(唯讀)及 Script Builder 指令 **Settle Point (churn series)**
(位於 **Flow** 分類下)形式提供。
