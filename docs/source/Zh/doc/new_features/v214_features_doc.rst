色覺辨認障礙模擬 + 碰撞檢查
==========================

狀態 UI 仰賴顏色——綠色「正常」對紅色「錯誤」的圓點、以顏色編碼的圖表圖例。對約 8% 有色覺辨認障礙
(CVD)的男性而言,這些可能難以分辨,而框架原本無從檢查。``cvd_simulate`` 補上無障礙 / 設計檢查
所需的兩個原語。

* :func:`simulate_cvd` ——把 ``(r, g, b)`` 顏色透過二色覺模擬矩陣(``protanopia`` /
  ``deuteranopia`` / ``tritanopia``)在給定 ``severity``(0 = 不受影響,1 = 完全二色覺)下映射。
* :func:`colors_collide` ——在某 CVD 類型下模擬兩個顏色,並回報它們是否變得太相似而難以區分
  (模擬後的感知 ``redmean`` 距離低於 ``threshold``)。
* :func:`color_distance` ——底層的 ``redmean`` 色差度量。

純標準函式庫——不需 numpy / OpenCV——以單純的 RGB tuple 運作,故能完整測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import simulate_cvd, colors_collide

    # 「錯誤紅」在綠色弱者眼中看起來如何?
    simulate_cvd((220, 40, 40), "deuteranopia")        # -> (r, g, b)

    # 我的正常綠與錯誤紅對他們是否可區分?
    report = colors_collide((60, 200, 60), (220, 60, 60), kind="deuteranopia")
    report["collide"]    # 若兩者易混淆則為 True
    report["distance"]   # 模擬後的感知距離

``simulate_cvd`` 接受友善別名(``protan`` / ``deutan`` / ``tritan``,或
``red`` / ``green`` / ``blue``)。``severity`` 在原色與完全二色覺模擬之間插值,
用於較輕微的異常三色覺。``colors_collide`` 回傳 ``{collide, distance, kind, severity,
simulated_left, simulated_right}``。

執行器指令
----------

``AC_simulate_cvd``(``rgb`` ``[r, g, b]`` 加上 ``kind`` / ``severity`` →
``{rgb}``)與 ``AC_colors_collide``(``left`` / ``right`` ``[r, g, b]`` 加上
``kind`` / ``severity`` / ``threshold`` → 報告)。RGB 輸入接受 JSON 清單。皆以對應的唯讀
``ac_*`` MCP 工具及 Script Builder 指令(位於 **Image** 分類下)形式提供。
