色彩直方圖指紋與變化偵測
========================

``image_dedup`` 以感知 aHash / dHash 做指紋——那是*空間性*的 64 位元雜湊,對顏色與主題變化很脆弱——而
``color_stats`` 只回傳單一平均 / 主要顏色。正規化的色彩*直方圖*是判斷「這是不是同一個畫面、調色盤是否改變」的標準
耐光照、耐縮放訊號:主題切換、內容重載、旋轉的橫幅——這些雜湊與單一主色都捕捉不到。

每個函式都在可注入的影像(ndarray / 路徑 / PIL,RGB)上執行,因此可對合成陣列做無頭測試。``cv2.calcHist`` /
``cv2.compareHist`` 屬於 OpenCV 核心;OpenCV + NumPy 透過 ``je_open_cv`` 引入。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (image_histogram, compare_histograms,
                                 histogram_changed)

    baseline = image_histogram("golden.png")          # 3 * bins 個浮點數(HSV)
    if histogram_changed("golden.png"):               # current = 實際螢幕
        print("the view changed")

    score = compare_histograms(baseline, image_histogram())   # 1.0 == 完全相同

``image_histogram`` 回傳逐通道正規化直方圖的平面清單(``space`` = ``hsv`` / ``rgb`` / ``gray``;每通道貢獻
``bins`` 個值)。``compare_histograms`` 支援 ``correlation`` / ``chisqr`` / ``intersection`` /
``bhattacharyya``(correlation / intersection 越高越相似;距離方法越高越不同)。``histogram_changed`` 比較
``reference`` 與 ``current``(預設為螢幕)並回傳布林值,會依相似 vs 距離方法自動翻轉門檻比較方向。

執行器命令
----------

``AC_image_histogram``(``source`` / ``bins`` / ``space`` / ``region`` → ``{bins, space, histogram}``)與
``AC_histogram_changed``(``reference`` / ``current`` / ``method`` / ``threshold`` / ``space`` / ``region`` →
``{changed, score}``)。它們以 MCP 工具 ``ac_image_histogram`` / ``ac_histogram_changed`` 以及 Script Builder 中
**Image** 分類下的命令提供。
