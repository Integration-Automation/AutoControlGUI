依顏色定位螢幕區域
==================

``color_stats`` 只*描述*區域的主要 / 平均顏色,``assert_pixel`` 檢查單一點及容差——兩者都不*定位*彩色區域。
當唯一訊號是顏色時(狀態燈、進度條填充、紅色錯誤橫幅),模板比對很脆弱。本功能將接近目標 RGB(在容差內)的
像素遮罩起來,並回傳相連區塊的邊界框。

遮罩與相連元件分析在可注入的 ``haystack`` 影像(ndarray / 路徑 / PIL)上執行,因此可在無真實螢幕下對合成陣列
做單元測試。OpenCV + NumPy 透過專案的 ``je_open_cv`` 相依引入。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import find_color_region, find_color_regions

    pill = find_color_region([0, 200, 0], tolerance=25)      # 綠色狀態藥丸
    if pill:
        click(*pill["center"])

    for banner in find_color_regions([200, 0, 0], min_area=500):
        print(banner["x"], banner["y"], banner["area"])      # 每個紅色區塊

``find_color_regions`` 為每個在 ``tolerance``(各通道)內接近 ``rgb`` 且至少 ``min_area`` 像素的區塊回傳
``{x, y, width, height, area, center}``,由大到小;``find_color_region`` 僅回傳最大的(或 ``None``)。
``haystack`` 預設為對選用 ``region`` 的螢幕擷取。

執行器命令
----------

``AC_find_color_region`` 接受 ``rgb``(JSON ``[r, g, b]`` 陣列)以及 ``tolerance`` / ``min_area`` / ``region``,
並回傳 ``{count, regions, best}``。它以 MCP 工具 ``ac_find_color_region`` 以及 Script Builder 中 **Image**
分類下的命令提供。
