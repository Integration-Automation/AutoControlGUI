顯示縮放 / 視覺 DPI 偵測
=======================

在 100% 顯示縮放下裁切的模板,在 150% DPI 的機器上不會逐像素吻合——一切都放大了 1.5 倍。
``visual_match.match_template`` *可以* 掃過多個縮放,但它只回傳單一最佳吻合的位置,並把各縮放的
分數丟棄。``scale_detect`` 保留整個剖面:它在一系列縮放下對 haystack 評分模板,並回報**哪個縮放
勝出、勝出多少**,讓自動化能推測有效的 UI 縮放 / DPI,以及該推測的信心。

* :func:`scale_sweep` ——逐縮放的分數剖面(每個縮放的最佳吻合),
* :func:`detect_scale` ——勝出的縮放作為 DPI 推測,並附信心 margin。

它對每個縮放重用 ``visual_match._score_map``(完整的 ``matchTemplate`` 表面,方向為越高越好),
因此來源可為任何 ndarray / 路徑 / PIL 影像(或存活螢幕)。cv2 / numpy 為延遲匯入。不匯入
``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import detect_scale, scale_sweep

    detect_scale("button.png", "screen.png")
    # {"scale": 1.5, "scale_percent": 150, "score": 0.98, "center": [...],
    #  "margin": 0.62, "candidates": [...]}

    scale_sweep("button.png", scales=[1.0, 1.25, 1.5, 1.75, 2.0])
    # [{"scale": 1.0, "score": .., "center": [..]}, {"scale": 1.25, ...}, ...]

``scales`` 預設為常見的 Windows 顯示縮放 ``(1.0, 1.25, 1.5, 1.75, 2.0)``。``margin`` 是勝出縮放
領先次佳者的幅度——margin 低代表推測模稜兩可。模板大於 haystack 的縮放會被略過;當沒有任何縮放
吻合時 ``detect_scale`` 回傳 ``None``。省略 ``haystack`` 即對存活螢幕比對(``region`` 套用於該
擷取)。

執行器指令
----------

``AC_detect_scale`` 與 ``AC_scale_sweep``(``template`` / ``haystack`` / ``region`` /
``scales`` / ``method``)。皆以唯讀 ``ac_*`` MCP 工具及 Script Builder 指令(位於 **Image**
分類下)形式提供。
