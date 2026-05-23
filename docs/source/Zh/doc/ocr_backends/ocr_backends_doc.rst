================================
OCR 後端
================================

AutoControl 提供三個可插拔的 OCR 引擎，共用同一組公開 API。
依照安裝環境與腳本要辨識的語言挑一個用就好：

.. list-table::
   :header-rows: 1
   :widths: 20 35 45

   * - 後端
     - 適用情境
     - 安裝方式
   * - ``tesseract``
     - ASCII / 西方語言、最輕量
     - ``pip install pytesseract`` + 把 ``tesseract.exe`` 放進 PATH
   * - ``easyocr``
     - CJK 但不想裝外部執行檔
     - ``pip install easyocr``\ （首次呼叫會下載約 64 MB 模型）
   * - ``paddleocr``
     - 中文／日文／韓文最高品質
     - ``pip install paddlepaddle paddleocr``

選擇後端的順序
==============

啟用的後端依照以下順序決定：

1. OCR 函式呼叫時傳入的 ``backend=`` 參數。
2. ``AUTOCONTROL_OCR_BACKEND`` 環境變數。
3. 自動偵測 — 依序嘗試 ``tesseract`` → ``easyocr`` → ``paddleocr``，
   挑出第一個 import 成功的。

實務上你只要 ``pip install`` 你要的那個後端，剩下的交給自動偵測即可::

   from je_auto_control import find_text_matches

   # 沒有 backend 參數、沒有環境變數 → 自動偵測
   matches = find_text_matches("登入")

要強制指定某個後端時::

   matches = find_text_matches("登入", backend="easyocr")

或在整個行程指定::

   $ AUTOCONTROL_OCR_BACKEND=paddleocr python my_script.py

語言代碼
========

每個後端原生使用的語言代碼不同，但公開 API 都接受同一組標準寫法
（Tesseract 風格），呼叫時會在邊界做翻譯：

.. list-table::
   :header-rows: 1

   * - AutoControl 標準代碼
     - Tesseract
     - EasyOCR
     - PaddleOCR
   * - ``eng``
     - ``eng``
     - ``en``
     - ``en``
   * - ``chi_tra`` / ``zh-TW``
     - ``chi_tra``
     - ``ch_tra``
     - ``chinese_cht``
   * - ``chi_sim`` / ``zh-CN``
     - ``chi_sim``
     - ``ch_sim``
     - ``ch``
   * - ``jpn``
     - ``jpn``
     - ``ja``
     - ``japan``
   * - ``kor``
     - ``kor``
     - ``ko``
     - ``korean``

其他語言（法／德／阿拉伯文……）直接傳該後端的原生代碼即可，會原樣傳入。

Tesseract 安裝注意
==================

Windows 必須另外安裝 Tesseract 執行檔（UB-Mannheim build 最常見）。
若 ``tesseract.exe`` 不在 ``PATH`` 上::

   from je_auto_control import set_tesseract_cmd
   set_tesseract_cmd(r"C:\Program Files\Tesseract-OCR\tesseract.exe")

語言檔（``*.traineddata``）放在 ``Tesseract-OCR\\tessdata\\`` 底下，
要哪個語言就從 `tessdata GitHub repo
<https://github.com/tesseract-ocr/tessdata>`_ 抓對應檔案複製進去。

EasyOCR / PaddleOCR 安裝注意
============================

兩者都會在第一次呼叫某個語言時懶下載神經模型，存放路徑：

- EasyOCR：``~/.EasyOCR/model/``\ （每個語言約 64 MB）。
- PaddleOCR：``~/.paddleocr/``\ （偵測 + 辨識模型合計約 50 MB）。

因此第一次呼叫會明顯比之後慢，建議在開機或測試 setup 預熱一次。

無 GUI 使用
===========

三個後端都符合 AutoControl「功能必須能脫離 GUI 使用」的規範。
公開 API 如下::

   from je_auto_control import (
       find_text_matches, locate_text_center, wait_for_text,
       click_text, read_text_in_region, find_text_regex,
   )

每個函式都吃同一組參數（``lang``、``region``、``min_confidence``、
``backend``、``case_sensitive``），回傳的 ``TextMatch`` 已自動換算
為絕對螢幕座標。

JSON 動作介面
=============

OCR 也透過 executor 對 JSON 動作檔開放::

   {"command": "AC_locate_text", "text": "登入", "lang": "chi_tra"}
   {"command": "AC_click_text",  "text": "確定", "backend": "easyocr"}

兩個指令的參數與 Python 端完全一致。

診斷
====

要確認當前環境有哪些後端可用::

   from je_auto_control.utils.ocr.backends import get_backend

   for name in ("tesseract", "easyocr", "paddleocr"):
       try:
           backend = get_backend(name)
           print(name, "可用" if backend.available else "不可用")
       except Exception as exc:  # noqa: BLE001
           print(name, "錯誤：", exc)
