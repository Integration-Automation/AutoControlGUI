==========================================
新功能 (2026-06-19) — 計時輸入巨集
==========================================

以時間保真度重播錄製的輸入,並用一個小型宣告式 DSL 編寫按住-放開的
組合鍵。純標準庫;走完整五層。兩者都透過可注入的 sink 與 sleep 派發,
因此能用假時鐘與記錄式 sink 做決定性單元測試。

.. contents::
   :local:
   :depth: 2


計時時間軸重播
==============

::

    from je_auto_control import replay_timeline

    events = [{"op": "move", "x": 10, "y": 10, "delta_ms": 0},
              {"op": "click", "x": 10, "y": 10, "delta_ms": 120},
              {"op": "key", "key": "a", "delta_ms": 80}]
    replay_timeline(events, speed=2.0)   # 兩倍速播放;間隔可夾限

每個事件的 ``delta_ms`` 間隔都會被遵守,並除以 ``speed``(且夾限在
``[min_gap, max_gap]``)。事件 ``op`` 為 ``move`` / ``click`` / ``scroll`` /
``press`` / ``release`` / ``key`` 之一。對應 ``AC_replay_timeline`` /
``ac_replay_timeline``。


輸入序列 DSL
============

::

    from je_auto_control import run_sequence

    run_sequence([
        {"op": "press", "key": "ctrl"},
        {"op": "repeat", "times": 3, "steps": [{"op": "key", "key": "a"}]},
        {"op": "wait", "ms": 50},
        {"op": "release", "key": "ctrl"},
    ])

用於按住-放開組合鍵與重複輸入的宣告式迷你語言:動作 op(``press`` /
``release`` / ``key`` / ``click`` / ``move`` / ``scroll``)加上控制 op
``{op: wait, ms}`` 與 ``{op: repeat, times, steps:[...]}``。回傳攤平後的
執行記錄。對應 ``AC_input_sequence`` / ``ac_input_sequence``。
