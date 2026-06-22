可操作性閘門——在操作前先等待就緒
==================================

現代 UI 框架(Playwright、Cypress、WebdriverIO)在每次點擊前都會執行*可操作性*檢查:目標必須存在、已停止移動、
為啟用狀態,且確實能接收事件(未被遮蓋)。AutoControl 先前沒有對應功能——``self_heal_click`` 定位後立即點擊,
``wait_until_screen_stable`` 只觀察*整個*畫面。``wait_actionable`` 把這四項檢查合成單一閘門,讓點擊落在真正就緒的
按鈕上,而非動畫中、停用、或被對話框擋住的狀態。

每個訊號都是可注入的 callable——``bbox_provider``(定位目標)、``region_sampler``(像素穩定 token)、
``enabled_probe``、``hit_tester``——再加上透過 :class:`GateConfig` 注入的 ``clock`` / ``sleep``,因此閘門完全
決定性且可無頭測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import wait_actionable, act_when_ready, GateConfig

    report = wait_actionable(
        bbox_provider=lambda: locate_button(),        # () -> (x, y, w, h) 或 None
        enabled_probe=lambda: not is_greyed_out(),
        config=GateConfig(timeout_s=8.0, stable_for_s=0.4))
    if report.actionable:
        click(*report.point)
    else:
        print("blocked:", report.reason)              # not visible / not stable / …

    # 或一次完成「等待 + 操作」(若始終未就緒則丟例外):
    act_when_ready(lambda point: click(*point), bbox_provider=locate_button)

``wait_actionable`` 回傳 :class:`ActionabilityReport`,含 ``actionable`` 以及各項檢查布林值
(``visible`` / ``stable`` / ``enabled`` / ``receives_events``)、目標 ``point``、``waited_s`` 與 ``reason``
(第一個失敗的檢查)。``act_when_ready`` 等待後呼叫 ``action(center_point)``,逾時則丟出
``AutoControlActionException``。

執行器命令
----------

``AC_wait_actionable`` 將閘門綁定到 ``template`` 影像(每次輪詢時定位),並取樣該區域像素以判斷穩定:
``timeout_s`` / ``stable_for_s`` / ``min_score`` / ``region`` → 回傳報告字典。它以 MCP 工具
``ac_wait_actionable`` 以及 Script Builder 中 **Flow** 分類下的命令提供。
