Agent 軌跡評估
==============

當自動化把控制權交給 LLM agent,「它還能運作嗎?」就變成「agent 是否走了可接受的路
徑?」。:func:`evaluate_trajectory` 依宣告式**評分標準(rubric)**為一次記錄的執行評
分,為 agent 回歸測試提供確定性、無相依的訊號。

*軌跡(trajectory)*是該次執行所採取步驟的有序清單 —— 每步是一個至少含 ``"action"``
名稱、可選含 ``"args"`` / ``"observation"`` 的 dict。*評分標準*為純資料(因此可自在地
存於 JSON action 檔或經 MCP 傳入):

================================ ===================================================
Rubric 鍵                        意義
================================ ===================================================
``required_actions``             必須全部出現的動作。
``ordered``                      搭配上者,還要求其相對順序。
``forbidden_actions``            絕不可出現的動作。
``max_steps``                    軌跡長度上限。
``success_contains``             必須出現在某個 observation 中的子字串。
================================ ===================================================

無頭 API
--------

.. code-block:: python

    from je_auto_control import evaluate_trajectory

    trajectory = [
        {"action": "AC_focus_window", "observation": "focused"},
        {"action": "AC_type_text", "observation": "typed"},
        {"action": "AC_click_mouse", "observation": "Saved successfully"},
    ]
    result = evaluate_trajectory(trajectory, {
        "required_actions": ["AC_type_text", "AC_click_mouse"],
        "forbidden_actions": ["AC_kill_process"],
        "max_steps": 10,
        "success_contains": "Saved",
    })
    assert result["passed"]            # 所有適用的檢查都通過
    print(result["score"], result["checks"])

``score`` 為通過的適用檢查佔比;``passed`` 僅在全部通過時為真;空 rubric 直接通過。
``checks`` 中每個項目為 ``{name, passed, detail}``,因此失敗時可精準指出被違反的期望。

執行器指令
----------

``AC_evaluate_trajectory`` 接受 ``trajectory`` 與 ``rubric``(從視覺化建構器傳入時為
JSON 字串,從 JSON action 檔 / MCP 傳入時為已解碼資料),回傳
``{passed, score, steps, checks}``。相同操作亦提供為 MCP 工具
``ac_evaluate_trajectory``,以及 Script Builder 中 **Agent** 分類下的指令。
