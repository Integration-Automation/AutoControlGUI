逐步評審特徵 + 規則式步驟評分
==============================

為代理的步驟評分需要把證據集中一處——動作是什麼、變了什麼、是否落在目標、宣告的後置條件
是否成立。``trajectory_eval`` 對*已完成的整條軌跡*依靜態準則評分,沒有逐步證據;
``agent_trace`` 發出 OTel span(權杖 / 延遲),而非決策品質;``agent_replay`` 保存
``{obs, action, result}`` 卻不評分。``critic_features`` 正是缺少的逐步層:它把 ``action_effect``
(有無效果、落在何處)、``observation_delta``(變了多少)與 ``postcondition``(預期結果是否成立)
組合成單一精簡記錄,並附上確定性的規則式評分器,使此功能可完整無頭運作——把可選的
LLM-as-judge 留給整合者。

純標準函式庫;組合既有純模組;確定性、可在無裝置下單元測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (build_critic_record, score_step_rule_based,
                                 to_judge_prompt)

    record = build_critic_record({"type": "click", "x": 480, "y": 260},
                                 before_elements, after_elements,
                                 postcondition={"appears": {"role": "dialog"}})
    score = score_step_rule_based(record)
    # {"outcome": True, "process_score": 1.0, "reasons": [...]}

    prompt = to_judge_prompt(record)   # 給 LLM-as-judge 的精簡文字

``build_critic_record`` 回傳 ``{action, effect, delta_counts}``,並在給定規格時附上
``postcondition`` 報告。``score_step_rule_based`` 回傳 ``{outcome, process_score, reasons}``
——``outcome`` 為二元成功(動作有效果*且*任何後置條件成立),``process_score`` 為依效果類別的
0..1 品質(後置條件失敗時減半)。``to_judge_prompt`` 把記錄渲染給外部評審。

執行器指令
----------

``AC_build_critic_record``(``action`` / ``before`` / ``after`` / ``postcondition`` /
``radius`` → 該記錄)與 ``AC_score_step``(``record`` → ``{outcome, process_score, reasons}``)。
兩者以 MCP 工具 ``ac_build_critic_record`` / ``ac_score_step``(唯讀)及 Script Builder 指令
**Build Critic Record** / **Score Step (rule-based)**(位於 **Native UI** 分類下)形式提供。
