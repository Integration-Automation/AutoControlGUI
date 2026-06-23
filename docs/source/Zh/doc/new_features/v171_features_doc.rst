次像素樣板比對精修
==================

每個比對器(``match_template`` / ``match_rotated`` / ``match_masked``)都直接從
``cv2.minMaxLoc`` 回傳*整數*像素座標。對拖曳把手、細滑桿、次像素渲染的目標或高 DPI 顯示器
而言,這種整數捨入是主要的點擊落點誤差來源。``subpixel_match`` 以拋物線擬合整數極大值周圍的
3x3 分數鄰域(x 與 y 各自獨立,即標準 NCC 次像素法),把峰值精修到像素的分數位。

本功能重用 ``visual_match._score_map``(公開比對器丟棄的完整 ``matchTemplate`` 曲面);
不重複任何比對程式。``haystack`` 可注入;分析可在合成陣列上單元測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import match_subpixel, refine_peak

    hit = match_subpixel("slider_thumb.png", min_score=0.8)
    if hit:
        # cx / cy 為浮點數——傳給支援次像素的拖曳 / 移動
        move_to(hit.cx, hit.cy)

    # 可用於任何分數曲面的擬合原語
    offset_x, offset_y = refine_peak(score_map, (peak_x, peak_y))

``match_subpixel`` 回傳 ``SubPixelMatch``(整數 ``x`` / ``y`` / ``width`` / ``height`` /
``score`` 加上浮點 ``cx`` / ``cy`` 與套用的 ``offset_x`` / ``offset_y``),或在低於
``min_score`` 時回傳 ``None``。``refine_peak`` 回傳峰值相對鄰點的 ``[-0.5, 0.5]`` 拋物線擬合
偏移——可用於任何相關性曲面。

執行器指令
----------

``AC_match_subpixel``(``template`` / ``min_score`` / ``region`` / ``method`` →
``{found, match}``)以 MCP 工具 ``ac_match_subpixel``(唯讀)及 Script Builder 指令
**Match Template (sub-pixel)**(位於 **Image** 分類下)形式提供。
