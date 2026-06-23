動作效果分類(我的點擊有沒有效果?)
====================================

代理點擊後最關鍵的問題是「這有沒有效果,而且是*正確的*效果嗎?」——但在*第一步*就回答這個
問題的功能並不存在。``screen_state.diff_snapshots`` 與 ``element_diff`` 回報變了什麼,卻從不
把變化歸因回該動作;``loop_guard`` 只在相同摘要重複 N 次後才標記 no-op(因此代理會先空轉
2–8 次);``actionability`` 純粹是*動作前*的閘門。``action_effect`` 補上這個迴圈:比對前後
觀測,並依動作的目標點分類結果,讓代理能立即反應。

判定為下列之一:``no_op``(無變化)、``changed_near_target``(變化發生在我們動作之處——按鈕被
按下)、``changed_elsewhere``(別處彈出意外對話框)、或 ``changed``(有變化但動作沒有可歸因的
座標點)。

純標準函式庫,作用於元素字典 + 動作記錄;重用 ``element_diff.match_elements`` 做重疊配對與
``observation_delta`` 的欄位變更檢查。完全確定性、可在無裝置下單元測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import classify_effect, effect_near_point, is_no_op

    verdict = classify_effect(before_elements, after_elements,
                              {"type": "click", "x": 480, "y": 260})
    if verdict.effect == "no_op":
        retry_or_repair()
    elif verdict.effect == "changed_elsewhere":
        handle_unexpected_dialog()

    if is_no_op(before_elements, after_elements):
        ...

``classify_effect`` 回傳 ``EffectVerdict``(``effect`` / ``changed_near_target`` /
``changed_count`` / ``changed_centers`` / ``reason``)。``effect_near_point`` 回答任一變化是否
落在任意點的 ``radius`` 內;``is_no_op`` 是布林捷徑。

執行器指令
----------

``AC_classify_effect``(``before`` / ``after`` / ``action`` / ``radius`` →
``{effect, changed_near_target, changed_count, changed_centers, reason}``)與
``AC_effect_near_point``(``before`` / ``after`` / ``point`` / ``radius`` → ``{near}``)。
兩者以 MCP 工具 ``ac_classify_effect`` / ``ac_effect_near_point``(唯讀)及 Script Builder 指令
**Classify Action Effect** / **Effect Near Point?**(位於 **Native UI** 分類下)形式提供。
