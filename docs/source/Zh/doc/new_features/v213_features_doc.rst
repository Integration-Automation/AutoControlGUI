等待應用程式閒置
================

在應用程式仍在忙碌時觸發的點擊——忙碌 / 等待游標出現、對話框正在繪製、長處理程序正在執行——
會被丟棄或誤點。``smart_waits`` 看*像素*安定;``app_idle`` 改看應用程式的*忙碌訊號*安定,
這更省成本且能在「有動畫但已閒置」的 UI 下運作。它重用 :class:`settle_detector.SettleTracker`:
每次輪詢在忙碌時餵入 ``1.0``、閒置時餵入 ``0.0``,當應用程式連續 ``quiet_samples`` 次讀到閒置
即返回(新的忙碌尖峰會重置該連續計數)。

* :func:`wait_until_app_idle` ——輪詢 ``busy_probe`` 直到應用程式安定閒置或逾時,``clock`` /
  ``sleep`` / ``busy_probe`` 皆可注入。
* :func:`idle_point` ——純函式:在已記錄的忙碌/閒置取樣序列中,首次變為安定閒置的索引。

預設 probe 回報 Windows 的忙碌 / 應用程式啟動游標;每個等待與安定決策都透過可注入接縫執行,
故能在沒有應用程式的情況下完整測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import wait_until_app_idle, idle_point

    # 啟動某程式,點擊前先等其忙碌游標安定
    start_exe("setup.exe")
    if wait_until_app_idle(quiet_samples=3, timeout_s=30)["idle"]:
        click_next()

    # 純函式:分析已記錄的忙碌/閒置軌跡
    idle_point([True, True, False, False, False], quiet_samples=3)   # 4

``wait_until_app_idle`` 回傳 ``{idle, polls, quiet_run, elapsed_s}``。傳入自訂 ``busy_probe``
(一個 ``() -> bool``)可對任何忙碌訊號設閘——spinner 影像比對、行程 CPU 門檻、無障礙「忙碌」旗標——
不限於游標。

執行器指令
----------

``AC_wait_until_app_idle``(``quiet_samples`` / ``timeout`` / ``interval`` →
``{idle, polls, quiet_run, elapsed_s}``,使用 Windows 忙碌游標)與
``AC_idle_point``(``busy_samples`` JSON 清單加上 ``quiet_samples`` → ``{index}``,純函式)。
皆以對應的唯讀 ``ac_*`` MCP 工具及 Script Builder 指令(位於 **Flow** 分類下)形式提供。
