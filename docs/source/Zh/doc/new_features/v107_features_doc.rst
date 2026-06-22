交易型 Outbox
=============

``events.cloud_events`` 立即且同步發送——在「完成工作」與「送出事件」之間若當機,事件就遺失;網路抖動也會
丟失(沒有持久化、沒有重試、沒有重播)。交易型 outbox 模式先持久化每個事件,稍後再以至少一次(at-least-once)
傳遞與死信上限來排空(drain),讓事件能在接收端故障時存活。

純標準函式庫(``json``);不匯入 ``PySide6``。傳遞用的 ``sink`` 以注入方式提供,儲存為記憶體內並具 JSON
持久化,因此排空在 CI 中完全具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import Outbox

    box = Outbox()
    box.enqueue({"type": "order.created", "id": 7})    # 已緩衝、待傳遞
    box.enqueue({"type": "order.paid", "id": 7})

    result = box.drain(post_to_webhook, max_batch=100, max_attempts=5)
    # {"sent": 2, "failed": 0, "remaining": 0}

    box.pending()        # 仍待傳遞的項目
    box.dead_letters()   # 已用盡重試次數的項目

``enqueue`` 將事件附加為待傳遞並回傳其 id。``drain`` 透過注入的 ``sink`` 傳遞至多 ``max_batch`` 個待傳遞項目;
``sink`` 拋出例外時,該項目維持待傳遞以供重試,直到 ``max_attempts``,之後被列為死信(連同錯誤一併記錄)。
傳遞為至少一次:若 ``sink`` 成功但在標記為已送出前被中斷,該項目會被重試。``save`` / ``load`` 以 JSON
持久化整個緩衝區,讓事件能在行程結束後存活。

執行器命令
----------

``AC_outbox_enqueue`` 回傳 ``{id, pending}``;``AC_outbox_pending`` 回傳 ``{pending}``。兩者使用具名實例登錄,
並以 MCP 工具(``ac_outbox_enqueue`` / ``ac_outbox_pending``)以及 Script Builder 中 **Flow** 分類下的命令提供。
排空需要可呼叫的 sink,因此維持為無頭 / API 操作。
