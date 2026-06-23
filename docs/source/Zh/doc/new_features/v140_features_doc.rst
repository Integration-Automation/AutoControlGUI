免模型文字區偵測(MSER)
========================

``shape_locator`` 找的是矩形輪廓(按鈕 / 卡片,不是文字),``locate_text`` 需要 Tesseract / Paddle 引擎*以及*要
搜尋的確切字串。兩者都無法在不跑 OCR、也不知道內容的情況下回答「畫面上哪裡有*任何*文字?」。``find_text_regions``
與 ``find_text_lines`` 以 MSER(最大穩定極值區域)找出字元 / 詞 / 行的區塊,讓腳本能裁切候選文字框餵給 OCR
(比全畫面 OCR 更快更準),或在未安裝 OCR 相依時單純偵測「某標籤出現了」。

在可注入的 ``haystack``(ndarray / 路徑 / PIL)上執行,因此可對合成陣列做無頭測試。``cv2.MSER_create`` 屬於
OpenCV 核心(不需 contrib);OpenCV + NumPy 透過 ``je_open_cv`` 引入。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import find_text_regions, find_text_lines

    # 裁切每一行文字,只對該長條做 OCR。
    for line in find_text_lines(y_tolerance=8):
        print(line["x"], line["y"], line["width"], line["height"])

    # 或逐字元 / 逐詞的區域。
    for box in find_text_regions(min_area=80):
        highlight(box["x"], box["y"], box["width"], box["height"])

``find_text_regions`` 為每個區域回傳 ``{x, y, width, height, area, center}``,由大到小;``merge`` 會聯集 MSER
逐字元的巢狀偵測,``min_area`` / ``max_area`` 去除雜點與整頁大小的區塊,``max_aspect`` 排除長條狀的分隔線。
``find_text_lines`` 將垂直中心在 ``y_tolerance`` 像素內的字元框歸為同一行,每行一個框、由上到下。空白畫面回傳空
清單(整框極值區域已被濾除)。

執行器命令
----------

``AC_find_text_regions``(``min_area`` / ``max_area`` / ``merge`` / ``max_aspect`` / ``region`` →
``{count, regions}``)與 ``AC_find_text_lines``(``y_tolerance`` / ``region`` → ``{count, lines}``)。它們以
MCP 工具 ``ac_find_text_regions`` / ``ac_find_text_lines`` 以及 Script Builder 中 **Image** 分類下的命令提供。
