卡迴圈守衛(Agent Loop 進度偵測)
================================

電腦操作最主要的失敗模式,是 agent 不斷重複一個沒有效果的動作而耗盡預算 —— 而模型通常
看不到自己的迴圈,因此必須從外部以**機械方式**偵測,藉由觀察 ``(tool, args, result)``
三元組串流。``LoopGuard`` 會標記三種模式:

- ``repeat`` —— 相同的 ``(tool, args)`` 連續觸發多次;
- ``ping_pong`` —— 兩個動作以 A-B-A-B 交替而毫無進展;
- ``no_op`` —— 觀察結果(截圖/狀態摘要)從未改變。

它與步數/時間預算(無法分辨有進展的迴圈與卡住的迴圈)以及離線軌跡評估互補。純標準函式
庫(``collections`` + ``hashlib``)、具確定性;不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import LoopGuard, digest_result

    guard = LoopGuard(warn=8, critical=15)
    for step in agent_steps:
        verdict = guard.observe(step.tool, step.args,
                                digest_result(step.screenshot))
        if verdict.level == "critical":
            break                       # 中止:卡住的迴圈
        if verdict.level == "warn":
            nudge_the_model(verdict.pattern)

``observe`` 回傳 ``{pattern, level, count}``,其中 ``level`` 在執行長度跨過門檻後為
``ok`` / ``warn`` / ``critical``。``count`` 為偵測到的執行長度。``digest_result`` 為截
圖/觀察結果(位元組或任何可 JSON 化的值)產生穩定的短雜湊。``reset`` 清除歷史。

執行器指令
----------

模組層級的預設守衛支撐 executor/MCP 介面,讓流程可跨步驟追蹤進度:

================================ ===================================================
指令                             效果
================================ ===================================================
``AC_loop_guard_observe``        餵入一步;回傳 ``{pattern, level, count}``。
``AC_loop_guard_reset``          清除預設守衛的歷史。
================================ ===================================================

相同操作亦提供為 MCP 工具(``ac_loop_guard_observe`` / ``ac_loop_guard_reset``),以及
Script Builder 中 **Agent** 分類下的指令。
