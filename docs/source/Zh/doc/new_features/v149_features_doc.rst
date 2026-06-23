感知式(YIQ)影像比對含反鋸齒抑制
====================================

``visual_regression.image_difference`` 計算原始逐通道最大差像素數,``ssim_compare`` 給出整體結構分數。兩者都未使用
*感知式*色彩度量,也都不忽略**反鋸齒邊緣**——那是跨 DPI 與字體微調時視覺比對誤報的首要來源。``perceptual_diff``
在 YIQ 空間比較像素(pixelmatch 的色彩度量,比 RGB 更接近人眼感知),並預設移除反鋸齒造成的單像素細邊差異
(形態學開運算),因此只計算*實心*變化區域。

在可注入的影像配對(ndarray / 路徑 / PIL)上執行,因此可對合成陣列做無頭測試。OpenCV + NumPy 透過 ``je_open_cv``
引入;沿用共用的連通元件輔助與 RGB 載入器。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import perceptual_diff, assert_perceptual

    result = perceptual_diff("actual.png", "golden.png", threshold=0.1)
    print(result.diff_pixels, result.diff_ratio, result.regions)

    # 把關視覺回歸測試(超出比例則拋例外)。
    assert_perceptual("actual.png", "golden.png", max_diff_ratio=0.01)

``perceptual_diff`` 回傳 ``PerceptualDiffResult``(``diff_pixels``、``total_pixels``、``diff_ratio``,以及變化叢集
的 ``regions`` 方框)。``threshold``(0..1)是 pixelmatch 靈敏度。``include_aa=True`` 會保留細邊差異而不抑制。
``assert_perceptual`` 在 ``diff_ratio`` 超過 ``max_diff_ratio`` 時丟出 ``AutoControlActionException``。不同尺寸的
影像會丟出 ``ValueError``。

執行器命令
----------

``AC_perceptual_diff``(``actual`` / ``expected`` / ``threshold`` / ``include_aa`` / ``max_diff_ratio`` →
``{diff_pixels, total_pixels, diff_ratio, regions}``;給定 ``max_diff_ratio`` 且超出時拋例外)。它以 MCP 工具
``ac_perceptual_diff`` 以及 Script Builder 中 **Image** 分類下的命令提供。
