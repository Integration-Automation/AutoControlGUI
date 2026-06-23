色彩感知樣板比對(HSV)
========================

``visual_match`` 的每個比對器都先轉灰階,因此形狀相同的紅色與綠色狀態指示燈對
``match_template`` 而言*無法區分*——具辨別力的訊號被丟棄了。``color_region`` 找*已知*顏色的
blob,卻無法以外觀對多色字形做樣板比對。``color_match`` 在 HSV 色相 / 飽和度通道上以色彩
*距離*度量(``TM_SQDIFF_NORMED``,而非相關——相關會把絕對色相正規化掉,使紅→綠邊與黑→藍邊
得分相同)進行比對,定位灰階比對會塌掉的色彩辨識目標。

本功能重用 ``color_region`` 的 RGB 載入器與 ``visual_match`` 的 resize / NMS / ``Match``。
``haystack`` 可注入;搜尋可在合成陣列上單元測試。不匯入 ``PySide6``。

註:如同任何視窗度量,*平坦*的單色 patch 在各通道無變異——純色 blob 請用
``find_color_region``;``color_match`` 適用於有色彩*結構*的目標。

無頭 API
--------

.. code-block:: python

    from je_auto_control import match_color, match_color_all

    # 定位紅色狀態 chip,而非同形狀的綠色
    hit = match_color("status_red.png", channels=("h", "s"), min_score=0.7)
    if hit:
        click(*hit.center)

    for m in match_color_all("tag_green.png", channels=("h",)):
        print(m.center, m.score)

``match_color`` 在選定 ``channels``(預設 ``("h", "s")``;平坦飽和度目標用 ``("h",)``)中回傳
最佳 ``Match``,或 ``None``。``match_color_all`` 回傳所有達到 ``min_score`` 的匹配,重疊以 NMS
移除。

執行器指令
----------

``AC_match_color``(``template`` / ``channels`` / ``min_score`` / ``scales`` / ``region`` →
``{found, match}``)與 ``AC_match_color_all``(另加 ``max_results`` / ``nms_iou`` →
``{count, matches}``)。兩者以 MCP 工具 ``ac_match_color`` / ``ac_match_color_all``(唯讀)及
Script Builder 指令 **Match Template (colour/HSV)** / **Match Template All (colour/HSV)**
(位於 **Image** 分類下)形式提供。
