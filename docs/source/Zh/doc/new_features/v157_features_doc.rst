一維條碼解碼
============

框架已能解碼 QR Code（``read_qr``），但缺少能讀取 *一維* 條碼（EAN-13 / EAN-8 /
UPC-A / Code-128）的功能——這些正是商品、庫存標籤與物流面單上最常見的條碼，也是
桌面或自助機自動化最需要從商品畫面讀取的資訊。``read_barcodes`` 透過 OpenCV 的
``cv2.barcode.BarcodeDetector`` 補上這一塊。

解碼步驟是一個**可注入接縫**：預設解碼器呼叫 OpenCV，但測試（或其他引擎）可以傳入
自己的 ``decoder`` 可呼叫物件，因此此功能可在無頭環境下完整單元測試，且能優雅降級
——若 OpenCV 編譯時未含 ``barcode`` 模組，僅回傳空清單而非拋出例外。不匯入
``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import read_barcodes

    # 解碼螢幕上目前所有一維條碼
    for code in read_barcodes():
        print(code["type"], code["text"], code["points"])

    # 限定區域，或改為解碼已存檔的影像
    read_barcodes(region=[0, 0, 400, 200])
    read_barcodes("label.png")

``read_barcodes(source=None, *, region=None, decoder=None)`` 回傳
``{"text", "type", "points"}`` 字典清單，每偵測到一個條碼一筆（``points`` 為影像
座標中的四角多邊形）。``source`` 可為影像路徑或陣列；省略時擷取螢幕（可選擇以
``region`` 裁切）。灰階轉換重用共用的 ``visual_match`` haystack 載入器，不新增
影像載入程式碼。

執行器指令
----------

``AC_read_barcodes``（``source`` / ``region`` → ``{count, barcodes}``）以 MCP 工具
``ac_read_barcodes``（唯讀）及 Script Builder 指令 **Read Barcodes (1-D)**（位於
**OCR** 分類下）形式提供。
