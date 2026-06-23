可攜式 Agent 軌跡記錄(錄製與重播)
====================================

``agent_trace`` 記錄 OpenTelemetry GenAI *span*(符記 / 延遲 / 成本)——那是觀測性,不是可重播的觀測→動作轉錄;
``trajectory_eval`` *評分*軌跡但未定義持久格式也無法重播;``semantic_recording`` 重播錄製的*人類輸入巨集*,而非
*agent* 決策。本功能加入 OmniTool 風格的「記錄軌跡以建立重播 / 訓練資料集」格式:``{step, observation, action,
result}`` JSONL,加上決定性的重播驅動器。

純標準函式庫 JSONL;重播驅動器接受可注入的 ``runner``(無需即時模型),因此完全可單元測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import record_step, to_jsonl, from_jsonl, replay_trace

    trace = []
    record_step(trace, observation="login screen",
                action=["AC_click_mouse", {"x": 120, "y": 80}])
    record_step(trace, observation="typed user", action=["AC_write",
                {"write_string": "alice"}], result={"ok": True})

    open("run.jsonl", "w").write(to_jsonl(trace))     # 持久化資料集

    # 之後——透過任意 runner 重播每一步(此處為測試用 fake)。
    results = replay_trace(from_jsonl(open("run.jsonl").read()),
                           runner=lambda action: do(action))

``record_step`` 附加一個有索引的 ``{step, observation, action[, result]}`` 條目;``to_jsonl`` / ``from_jsonl`` 以
換行分隔 JSON 往返;``replay_trace`` 透過 ``runner(action)`` 執行每一步的 ``action``,並依序回傳
``{step, action, result}`` 結果。

執行器命令
----------

``AC_replay_trace`` 透過執行器執行每一步的 ``action``(AC 動作清單)來重播 ``trace``(JSON 陣列或 JSONL),回傳
``{count, results}``。它以 MCP 工具 ``ac_replay_trace``(有副作用)以及 Script Builder 中 **Flow** 分類下的命令提供。
