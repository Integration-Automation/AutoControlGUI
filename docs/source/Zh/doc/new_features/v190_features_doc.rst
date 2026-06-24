視覺顯著度(該看哪裡——spectral-residual)
==========================================

當沒有模板、沒有已知顏色、也沒有文字可 OCR 時,agent 仍需要一個*該看哪裡*的線索——也就是從
周遭凸顯出來的區域(彈出視窗、徽章、被反白的列)。``saliency`` 計算 spectral-residual 顯著度圖
(Hou & Zhang 2007)——``log`` 振幅減去其區域平均,再透過相位重建——並轉成排序後的顯著方框。

* :func:`saliency_map` ——正規化(0–1)的顯著度圖(ndarray),
* :func:`salient_regions` ——排序後的顯著方框 ``{x, y, width, height, center, score}``
  (以來源像素座標表示),
* :func:`most_salient` ——單一最顯著的區域(第一個該看的地方)。

此轉換為純 ``numpy`` FFT——``cv2.saliency`` 位於被禁用的 opencv-contrib 套件,故在 base opencv
上重新實作。它重用 ``visual_match`` 的灰階載入器(任何 ndarray / 路徑 / PIL 影像,或存活螢幕)與
``cv2_utils.blobs.connected_boxes`` 做區域擷取。cv2 / numpy 為延遲匯入。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import saliency_map, salient_regions, most_salient

    most_salient("screen.png")
    # {"x": 612, "y": 40, "width": 180, "height": 36, "center": [702, 58],
    #  "score": 0.82}

    for region in salient_regions("screen.png"):   # 最顯著者在前
        ...

    sal = saliency_map("screen.png")               # (64, 64) float32,範圍 0..1

區域預設以顯著度圖的 ``mean + 2·std`` 為門檻(可傳 ``threshold`` 覆寫),以 ``connected_boxes``
擷取,並縮放回來源的像素座標。``size`` 是計算顯著度所用的(較小)解析度。顯著度是粗略的注意力
線索,而非精確偵測器——用它來*縮小*接著由模板 / OCR 比對的範圍。

執行器指令
----------

``AC_salient_regions`` 與 ``AC_most_salient``(``source`` / ``region`` / ``size`` /
``threshold`` / ``min_area``)。皆以唯讀 ``ac_*`` MCP 工具及 Script Builder 指令(位於 **Image**
分類下)形式提供。
