影像品質評分(銳利度 / 對比 / 亮度門檻)
=======================================

OCR 與模板比對在模糊、褪色或太暗的擷取畫面上會悄悄失敗——定位回傳空值,呼叫端無法分辨是元素
*不存在*還是畫面*無法辨識*。``image_quality`` 量測三項會破壞辨識的指標並據以把關:

* **sharpness(銳利度)**——Laplacian 的變異數(低 = 模糊 / 失焦),
* **contrast(對比)**——灰階的標準差(低 = 褪色),
* **brightness(亮度)**——灰階平均 0–255(太低 = 太暗,太高 = 過曝)。

:func:`image_quality` 回傳原始指標,:func:`is_blurry` 是常用的一行式,:func:`quality_gate` 把
指標轉成通過 / 失敗的判定並附上具名問題,讓腳本可以拒絕對壞畫面做 OCR(或先做前處理)。它重用
``visual_match`` 的灰階載入器,因此來源可為任何 ndarray / 路徑 / PIL 影像(省略時則為存活螢幕);
cv2 / numpy 為延遲匯入。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import image_quality, is_blurry, quality_gate

    image_quality("frame.png")
    # {"sharpness": 842.1, "contrast": 58.3, "brightness": 131.0}

    if is_blurry("frame.png", threshold=100):
        ...  # 在 OCR 前重新擷取 / 銳化

    gate = quality_gate("frame.png", min_sharpness=100, min_contrast=12)
    # {"sharpness": .., "contrast": .., "brightness": .., "passed": False,
    #  "issues": ["blurry", "too_dark"]}

``quality_gate`` 會標記 ``blurry`` / ``low_contrast`` / ``too_dark`` /
``too_bright``;只有在沒有任何問題時 ``passed`` 才為 True。``region`` 套用於存活螢幕擷取(省略
``source`` 即評分螢幕)。門檻可調整;預設值適合一般 UI 截圖。

執行器指令
----------

``AC_image_quality``(``source`` / ``region``)與 ``AC_quality_gate``(另加
``min_sharpness`` / ``min_contrast``)。皆以唯讀 ``ac_*`` MCP 工具及 Script Builder 指令
(位於 **Image** 分類下)形式提供。
