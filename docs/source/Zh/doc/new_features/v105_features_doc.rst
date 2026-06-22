逐串流序號間隙偵測
================

沒有東西追蹤每個串流的單調序號以偵測遺漏、亂序或重複的訊息。``dedup_window`` 說「之前看過這個 id」;
本功能補上互補的一面:分類每個序號,並追蹤每個串流的未決間隙與 high-water 標記。

純標準函式庫;不匯入 ``PySide6``。狀態為記憶體內且完全可注入,因此偵測在 CI 中具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import SequenceTracker

    tracker = SequenceTracker()
    tracker.observe("orders", 1)      # {"status": "ok", ...}
    tracker.observe("orders", 4)      # {"status": "gap", "missing": [2, 3]}
    tracker.observe("orders", 3)      # {"status": "reorder", "missing": [2]}
    tracker.gaps("orders")            # [2]
    tracker.high_water("orders")      # 4

``observe`` 回傳 ``{status, seq, missing}``,status 為 ``ok``(順序下一個或首次)、``duplicate``(已看過)、
``gap``(序號被跳過 —— 記為遺漏)或 ``reorder``(較早的遲到序號,可填補間隙)。``gaps`` 列出未決遺漏序號,
``high_water`` 為最高已見序號。各串流以 ``stream_id`` 獨立追蹤。

執行器命令
----------

``AC_sequence_observe`` 在具名追蹤器中觀察某 ``stream_id`` 的 ``seq`` 並回傳分類。它使用具名實例登錄,
並以 MCP 工具 ``ac_sequence_observe`` 以及 Script Builder 中 **Flow** 分類下的命令提供。
