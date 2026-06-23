失敗 / 無效果動作的修復策略引擎
================================

當動作沒有效果或落點錯誤時,代理需要一個*策略*決定下一步該試什麼——重新定位重試、微調座標、
把目標捲入視野、等待重試,或放棄並升級。``self_healing`` / ``locator_repair`` 只修復*無法
解析*的定位器(找不到元素);當元素找到並點擊了卻無效果時,它們無能為力。``loop_guard`` 只
*偵測*卡住的迴圈——沒有戰術選擇或退避。``step_repair`` 正是缺少的控制器:它消費一個效果判定
(例如來自 ``action_effect``),並驅動有界的重試迴圈,每輪選擇下一個尚未嘗試的戰術。

純標準函式庫狀態機;每個副作用——執行動作、驗證、套用戰術、睡眠——都是注入的可呼叫物件,
因此迴圈完全確定性、可在無裝置下單元測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (plan_repair, run_with_repair, RepairPolicy,
                                 classify_effect)

    # 只要規劃
    plan_repair("no_op")              # ['wait_retry', 'relocate', 'nudge']
    plan_repair("changed_elsewhere")  # ['escalate']

    # 以注入接縫驅動迴圈
    outcome = run_with_repair(
        act=lambda: click(*target),
        verify=lambda: not is_no_op(before(), after()),
        apply_tactic=apply,                 # 例如 relocate / nudge 目標
        verdict_for=lambda: classify_effect(before(), after(), action).effect,
        policy=RepairPolicy(max_attempts=3))
    print(outcome.ok, outcome.tactics_used)

``plan_repair`` 回傳某判定(字串如 ``no_op`` / ``changed_elsewhere`` 或 ``EffectVerdict``
字典)的有序戰術,截到 ``max_attempts``;``next_tactic`` 回傳下一個尚未試過的。
``run_with_repair`` 執行 ``act`` 然後 ``verify``;失敗時套用戰術直到成功或耗盡,回傳
``RepairOutcome``(``ok`` / ``attempts`` / ``tactics_used`` / ``detail``)。``RepairPolicy``
限制嘗試次數並列出允許的戰術。

執行器指令
----------

``AC_plan_repair``(``verdict`` / ``max_attempts`` → ``{count, tactics}``)以 MCP 工具
``ac_plan_repair``(唯讀)及 Script Builder 指令 **Plan Repair Tactics**(位於 **Native UI**
分類下)形式提供。(實際的 ``run_with_repair`` 迴圈因接受注入可呼叫物件,由 Python 驅動。)
