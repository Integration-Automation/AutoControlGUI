時間視窗去重
==========

``work_queue`` 只對 ``new`` / ``in_progress`` 參照去重 —— 一旦項目完成,同一參照又會再入列,重送的
webhook 也會被重複處理。本功能補上缺少的「最近 N 秒看過這個 id → 丟棄」收件匣,把至少一次投遞轉換成
視窗內恰好一次。

純標準函式庫;不匯入 ``PySide6``。時鐘可注入,因此 TTL 驅逐在 CI 中完全具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import DedupWindow

    inbox = DedupWindow(ttl_s=3600)
    if inbox.check_and_mark(event_id):
        process(event)           # 視窗內首次
    else:
        skip(event)              # 重複 / 重送

``check_and_mark`` 在視窗內首次看到某 id 時原子性回傳 ``True``(並標記),重複則回傳 ``False``。``seen`` /
``mark`` 是分離的查詢/記錄兩半,``purge_expired`` 丟棄過期項目,``size`` 回報有效數量。超過 ``ttl_s`` 的
項目會在每次操作時驅逐,因此視窗保持有界。

執行器命令
----------

``AC_dedup_check`` 在具名視窗(TTL ``ttl_s``)中對 ``message_id`` 做 check-and-mark,回傳
``{first_seen, size}``。它使用具名實例登錄,並以 MCP 工具 ``ac_dedup_check`` 以及 Script Builder 中
**Flow** 分類下的命令提供。
