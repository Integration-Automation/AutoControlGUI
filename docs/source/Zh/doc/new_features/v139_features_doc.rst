HSV 色彩空間分割
================

``find_color_region`` 在 RGB 以各通道 ± 容差框遮罩,這在經典情境會失效:狀態燈、強調色或主題色調是「同一個顏色」
但*亮度*不同。HSV 把色相與飽和度 / 明度分離,因此「色相帶 + 飽和度 / 明度下限」可在不同光照下捕捉某顏色的所有色階。
本功能加入 HSV 遮罩與區塊框,沿用共用的連通元件輔助函式,並正確處理紅色的色相環繞(跨越 0/180 邊界)。

在可注入的 ``haystack``(ndarray / 路徑 / PIL,RGB)上執行,因此可對合成陣列做無頭測試。OpenCV + NumPy 透過
``je_open_cv`` 引入。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import dominant_hue_regions, segment_hsv, color_mask

    # 每個紅色區域——不論明暗、不論光照(已處理紅色環繞)。
    for r in dominant_hue_regions(hue=0, hue_tol=10, sat_min=80, val_min=80):
        click(*r["center"])

    # 或明確的 HSV 帶(H 0-179、S/V 0-255)。
    greens = segment_hsv(lower_hsv=[40, 80, 80], upper_hsv=[80, 255, 255])
    mask = color_mask(lower_hsv=[40, 80, 80], upper_hsv=[80, 255, 255])

``dominant_hue_regions`` 只限制色相(± ``hue_tol``)再加 ``sat_min`` / ``val_min`` 下限以略過灰階,為每個區塊回傳
``{x, y, width, height, area, center}``,由大到小——因此能在任何亮度下找到某顏色,不像 RGB 框。``segment_hsv`` 接受
明確的 ``lower_hsv`` / ``upper_hsv`` 帶;``color_mask`` 回傳原始 uint8 遮罩。

執行器命令
----------

``AC_segment_hsv``(``lower_hsv`` / ``upper_hsv`` / ``min_area`` / ``region``)與
``AC_dominant_hue_regions``(``hue`` / ``hue_tol`` / ``sat_min`` / ``val_min`` / ``min_area`` / ``region``),
皆回傳 ``{count, regions, best}``。它們以 MCP 工具 ``ac_segment_hsv`` / ``ac_dominant_hue_regions`` 以及 Script
Builder 中 **Image** 分類下的命令提供。
