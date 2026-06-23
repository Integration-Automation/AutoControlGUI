結構相似度(SSIM)比較
========================

框架已能以原始像素差(``diff_screenshots``)與顏色直方圖(``detect_drift``)比較畫面——但兩者都不是*結構性*的。
像素差會因為一像素位移或人眼會忽略的亮度變化而誤報;直方圖則對版面無感(把畫面左右兩半互換,它毫無變化)。
SSIM 是標準的視覺回歸度量:容忍輕微光照變化,對結構變化(文字被編輯、元素移動或消失)敏感。``ssim_compare``
回傳單一 0..1 分數,``ssim_changed_regions`` 則回傳*哪裡*真正變了的方框。

它是純 NumPy + OpenCV 實作(不需 scikit-image),在可注入的影像配對上執行,因此可在無真實螢幕下對合成陣列做
單元測試。OpenCV + NumPy 透過 ``je_open_cv`` 引入。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import ssim_compare, ssim_changed_regions

    # 以黃金截圖把關視覺回歸測試。
    score = ssim_compare("golden.png")           # current = 實際螢幕
    assert score > 0.98

    # 忽略即時時鐘 / 閃爍游標,再列出哪裡移動了。
    for box in ssim_changed_regions("golden.png", ignore=[[0, 0, 120, 30]]):
        print(box["x"], box["y"], box["width"], box["height"])

``ssim_compare`` 回傳整張影像的平均 SSIM(``1.0`` = 完全相同);``current`` 預設為對選用 ``region`` 的螢幕擷取。
``ignore`` 是一組從分數與變化偵測中排除的 ``[x, y, w, h]`` 方框。``ssim_changed_regions`` 標記局部不相似度
``1 - SSIM`` 超過 ``threshold`` 的像素,將相連者(``min_area`` 以上)分群,回傳 ``{x, y, width, height, area,
center}``,由大到小。比較兩張不同尺寸的影像會丟出 ``ValueError``。

執行器命令
----------

``AC_ssim_compare``(``reference`` / ``current`` / ``ignore`` / ``region`` →
``{score}``)與 ``AC_ssim_changed_regions``(另有 ``threshold`` / ``min_area`` →
``{count, regions}``)。它們以 MCP 工具 ``ac_ssim_compare`` / ``ac_ssim_changed_regions`` 以及 Script Builder 中
**Image** 分類下的命令提供。
