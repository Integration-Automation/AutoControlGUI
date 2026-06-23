邊緣形狀(Chamfer)樣板比對
============================

當同一個控制項以不同填充、漸層、主題或抗鋸齒繪製時,強度相關(``visual_match``)會被拉低;
而 ORB 特徵比對(``feature_match``)需要角點紋理,扁平設計的圖示——漢堡選單、單純的箭號
——根本沒有。``edge_match`` 改以*邊緣形狀*定位樣板:對兩張影像跑 Canny,對場景邊緣建立
距離轉換,再把樣板邊緣滑過它,以「每個樣板邊緣到最近場景邊緣的平均距離」為每個位置評分
(Chamfer 比對)。完美對齊的成本約為 0,與形狀如何填充或著色無關。

本功能重用 ``visual_match`` 的灰階載入器 / resize / NMS / ``Match`` 與 ``edge_lines`` 的
Canny 預設,因此不重複任何比對或幾何程式。``haystack`` 可注入(ndarray / 路徑 / PIL);
搜尋可在合成陣列上單元測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import edge_match, edge_match_all, chamfer_distance

    # 不論填色 / 主題,找出扁平圖示
    hit = edge_match("chevron.png", min_score=0.7)
    if hit:
        click(*hit.center)

    for m in edge_match_all("divider_handle.png", min_score=0.8):
        print(m.center, m.score)

    print(chamfer_distance("logo_outline.png"))   # 0 = 邊緣完全重合

``edge_match`` 在指定 ``scales`` 中回傳最佳 ``Match``(score = ``1 / (1 + 平均邊緣距離)``,
故 1.0 為完美輪廓匹配)或 ``None``。``edge_match_all`` 回傳所有達到 ``min_score`` 的匹配,
重疊以 NMS 移除。``chamfer_distance`` 回傳最佳對齊處的平均邊緣間距(0 = 輪廓重合)。

執行器指令
----------

``AC_edge_match``(``template`` / ``min_score`` / ``scales`` / ``region`` →
``{found, match}``)與 ``AC_edge_match_all``(另加 ``max_results`` / ``nms_iou`` →
``{count, matches}``)。兩者以 MCP 工具 ``ac_edge_match`` / ``ac_edge_match_all``(唯讀)及
Script Builder 指令 **Match Template (edge shape)** / **Match Template All (edge shape)**
(位於 **Image** 分類下)形式提供。
