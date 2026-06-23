動作前接地防護
==============

``guardrail`` 掃描文字找提示注入、``loop_guard`` 偵測卡住的迴圈——但兩者都不在派發前驗證*座標動作*。agent 迴圈會
執行模型回傳的任何東西,毫無邊界或目標檢查,因此幻覺出的 ``(9999, -5)`` 點擊會打到空處,而偏 5 像素的點擊會錯過
按鈕。``validate_action`` 加入「執行前偵測錯位動作」防護:拒絕螢幕外點擊,並把接近但偏離的座標吸附到最近已知元素
的中心。

純標準函式庫幾何,作用於純元素字典(``x`` / ``y`` / ``width`` / ``height``),因此完全可單元測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import validate_action, snap_to_element, in_bounds

    check = validate_action(model_action, screen_size=(1920, 1080), targets=elements)
    if not check["ok"]:
        print("rejected:", check["reason"])         # 例如 "out of bounds"
    else:
        x, y = check["snapped"] or (model_action["x"], model_action["y"])
        click(x, y)                                  # 已吸附到真正的按鈕

``in_bounds(x, y, screen_size)`` 是螢幕邊界判斷式;``snap_to_element`` 回傳某點所在(或在 ``max_dist`` 內最近)
元素的中心,否則 ``None``;``validate_action`` 結合兩者,回傳 ``{ok, reason, snapped}``——拒絕越界座標,並在提供
``targets`` 時吸附接近偏離者。沒有座標的動作一律通過。

執行器命令
----------

``AC_validate_action``(``action`` / ``screen`` / ``targets`` → ``{ok, reason, snapped}``;``screen`` 預設為實際
螢幕)。它以 MCP 工具 ``ac_validate_action`` 以及 Script Builder 中 **Native UI** 分類下的命令提供。
