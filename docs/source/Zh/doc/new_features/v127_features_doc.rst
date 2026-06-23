具信心分數的模板比對
====================

本專案的模板比對器(``cv2_utils`` 經由 ``je_open_cv.find_object``)為單一尺度且僅回傳邊界框——其內部計算的
相關性*分數*被丟棄。因此先前無法為候選排名、設定信心門檻並讀回*比對程度*、在 UI 經 DPI / 縮放時找到控制項,
或列舉*每一個*出現處。本功能加入這些,類似 PyAutoGUI 的 ``confidence`` / ``locateAll`` 與 SikuliX 的
``similarity`` / ``findAll``。

比對接受可注入的 ``haystack`` 影像(ndarray / 路徑 / PIL),因此可在無真實螢幕下對合成陣列做單元測試——僅預設
(擷取螢幕)為裝置相依。OpenCV + NumPy 透過專案的 ``je_open_cv`` 相依引入。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import match_template, match_template_all, best_matches

    m = match_template("button.png", min_score=0.85, scales=(0.9, 1.0, 1.1))
    if m:
        print(m.score, m.scale, m.center)     # 信心 + DPI 尺度 + 點擊點

    for hit in match_template_all("row_handle.png", min_score=0.8):
        click(*hit.center)                     # 每個出現處,重疊已移除

``match_template`` 回傳達到 ``min_score`` 的單一最佳 :class:`Match`(``x`` / ``y`` / ``width`` / ``height`` /
``score`` / ``scale`` / ``center``),並搜尋 ``scales`` 中每個尺度以容忍 DPI / 縮放。``match_template_all``
回傳所有命中,以非極大值抑制(``nms_iou``)合併重疊偵測並以 ``max_results`` 設上限。``best_matches`` 回傳依
分數排序的前 N 個(不論門檻,供調校)。

執行器命令
----------

``AC_match_template`` 回傳 ``{found, match}``(match dict 帶有分數);``AC_match_template_all`` 回傳
``{count, matches}``。兩者皆以 MCP 工具(``ac_match_template`` / ``ac_match_template_all``)以及 Script Builder
中 **Image** 分類下的命令提供。
