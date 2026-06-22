遮罩模板比對(忽略背景)
========================

一般模板比對會計分模板的*每個*像素,因此從某背景裁切出的圖示無法比對到同一圖示在不同背景上的情形——
工具列圖示在 hover 與閒置按鈕上、游標疊在任意內容上、Logo 在主題化表面上。``match_masked`` 只計算你標記為
相關的像素:明確的灰階 ``mask``(非零 = 使用),或——若傳入 RGBA 模板——其 alpha 通道。透明 /「不在乎」的
像素就不會再把分數拉低。

它沿用與 :doc:`v127_features_doc` 相同的 ``Match`` 結果(左上角、尺寸、``score``、``center``),並在可注入的
``haystack``(ndarray / 路徑 / PIL)上執行,因此可對合成陣列做單元測試。比對使用 OpenCV 的遮罩
``TM_CCORR_NORMED``(唯一能接受遮罩且不產生 NaN 的正規化度量);非有限值會被歸零。OpenCV + NumPy 透過
``je_open_cv`` 引入;不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import match_masked, match_masked_all

    # 帶透明度的 PNG 圖示——其 alpha 自動作為遮罩。
    hit = match_masked("save_icon.png", min_score=0.9)
    if hit:
        click(*hit.center)

    # 明確遮罩:只比對 mask.png 的白色像素。
    for hit in match_masked_all("cursor.png", mask="cursor_mask.png",
                                min_score=0.95):
        print(hit.x, hit.y, hit.score)

``match_masked`` 回傳達到 ``min_score`` 的單一最佳 ``Match``(或 ``None``);``match_masked_all`` 回傳每個
比對,以非極大值抑制移除重疊,分數由高到低,上限 ``max_results``。遮罩形狀與模板不符會丟出 ``ValueError``。

執行器命令
----------

``AC_match_masked`` / ``AC_match_masked_all`` 接受 ``template``(及選用 ``mask``)以及
``min_score`` / ``region``(*all* 形式另有 ``max_results`` / ``nms_iou``)。它們以 MCP 工具
``ac_match_masked`` / ``ac_match_masked_all`` 以及 Script Builder 中 **Image** 分類下的命令提供。
