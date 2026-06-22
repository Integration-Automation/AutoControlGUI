影像前處理(供 OCR / 模板比對)
================================

``locate_text`` / ``ocr_read_structure`` 與 ``match_template`` 是把*原始*螢幕擷取直接餵給 OCR 引擎或比對器。
小字、暗色主題、低對比與略為旋轉的截圖會嚴重影響兩者——而框架先前完全沒有前處理接縫。本功能加入標準前處理
流程——灰階 → 放大 → 二值化 → 去歪斜 → 去噪 → CLAHE 對比——以倍增你已在使用的 OCR 與比對功能的準確度。

每個函式都在可注入的 ``haystack`` 影像(ndarray / 路徑 / PIL,預設為對 ``region`` 擷取螢幕)上執行並回傳
NumPy ndarray,因此可對合成陣列做單元測試。OpenCV + NumPy 透過 ``je_open_cv`` 引入。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import preprocess_image, binarize, deskew, upscale

    # 一次性流程,再對清理後的影像做 OCR。
    clean = preprocess_image("receipt.png", steps=("grayscale", "upscale",
                                                    "deskew", "binarize"), scale=2.0)

    # 或個別組合各步驟。
    bw = binarize("panel.png", method="adaptive_gaussian", block_size=41)
    straight = deskew("scan.png", max_angle=10.0)
    big = upscale("tiny_label.png", scale=3.0, interp="lanczos")

基礎元件有 ``to_grayscale``、``upscale``(``scale`` / ``interp``)、``binarize``(``method`` =
``otsu`` / ``adaptive_mean`` / ``adaptive_gaussian``)、``denoise``、``enhance_contrast``(CLAHE)、``deskew``
以及 ``detect_skew_angle``(回傳量測到的文字歪斜角度,夾在 ``±max_angle``)。``preprocess_image`` 依序串接任意
具名 ``steps``——``grayscale``、``upscale``、``binarize``、``denoise``、``deskew``、``contrast``;未知步驟名稱
會丟出 ``ValueError``。

執行器命令
----------

``AC_preprocess_image`` 執行流程並把結果*寫入* ``output_path``(因此可從 JSON / MCP / builder 使用):
``source`` 為影像路徑(預設為對 ``region`` 擷取螢幕)、``steps`` 為有序清單(或逗號字串),另有 ``scale`` /
``block_size`` / ``c``;回傳 ``{path, width, height}``。它以 MCP 工具 ``ac_preprocess_image`` 以及 Script
Builder 中 **Image** 分類下的命令提供。
