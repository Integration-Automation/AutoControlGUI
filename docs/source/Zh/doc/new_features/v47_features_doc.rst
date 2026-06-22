任務 / 流程探勘(自動化候選發現)
================================

企業 RPA 套件透過探勘錄製的桌面動作中頻繁、可重複的子序列來*發現*該自動化什麼。
AutoControl 一直錄製豐富的動作日誌卻從未分析;``mine_action_log`` 將日誌轉成一份排序後
的自動化候選清單 —— 它計數重複的指令 n-gram、建立 directly-follows 圖,並依每段重複執
行的**次數與長度**為候選評分。

它作用於本專案的動作清單結構(每步為 ``["AC_name", {...}]`` 對或 ``{"command":
"AC_name", ...}`` 對映)。純標準函式庫(``collections``);不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import mine_action_log, directly_follows

    report = mine_action_log(recorded_actions, min_len=2, max_len=5, min_count=3)
    report.total_actions
    for cand in report.candidates[:5]:        # 由高至低
        print(cand.pattern.actions, cand.pattern.count, cand.score)

    directly_follows(recorded_actions)        # {(a, b): 邊計數} 流程圖

``find_repeated_sequences`` 回傳原始的 n-gram :class:`SequencePattern` 清單;
``rank_automation_candidates`` 為其評分(``count × length`` —— 越多、越長的重複排名越
高)。一個經常重現且橫跨多步的候選,是「把它抽成可重用 skill」的強烈訊號。

執行器指令
----------

``AC_mine_actions`` 接受 ``actions``(清單,或視覺化建構器傳入的 JSON 字串清單)以及
``min_len`` / ``max_len`` / ``min_count``,並回傳 ``{total_actions, patterns,
candidates}``。相同操作亦提供為 MCP 工具 ``ac_mine_actions``,以及 Script Builder 中
**Report** 分類下的指令。
