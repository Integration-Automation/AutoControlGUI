剪貼簿格式檢視(分類 / 比較可用格式)
====================================

剪貼簿通常同時以多種格式保存*相同*內容——從 Word 複製會提供 ``CF_UNICODETEXT`` +
``HTML Format`` + ``Rich Text Format``,複製檔案會提供 ``CF_HDROP``,截圖會提供 ``CF_DIB``。
知道*目前有哪些格式*(且不消耗任何一個)能讓自動化判斷可以貼上什麼,比較兩份快照則能偵測
剪貼簿的形態何時改變。``clipboard_formats`` 加入:

* :func:`classify_format` / :func:`classify_formats` ——把標準 ``CF_*`` id 與已註冊格式名稱
  對應到友善類別(text / image / files / html / rtf / csv / audio……),
* :func:`diff_formats` ——純粹的監看原語:兩份快照之間的 ``{added, removed, changed}``,
* :func:`list_clipboard_formats` / :func:`clipboard_formats` ——列舉存活的剪貼簿
  (``EnumClipboardFormats``)並加以分類。

分類器與比較器為純函式(可在任何平台單元測試);只有存活列舉為 Win32(其他平台拋出
``RuntimeError``)。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (classify_formats, diff_formats,
                                 clipboard_formats)

    classify_formats([13, {"id": 49383, "name": "HTML Format"}])
    # {"categories": ["html", "text"], "has_text": True, "has_image": False, ...}

    diff_formats([13, 1], [13, 15])     # {"added": [files], "removed": [text], ...}

    clipboard_formats()                  # 存活剪貼簿摘要(Windows)

描述子可為 id(``13``)、``{"id": ..., "name": ...}`` 字典,或 ``(id, name)`` 元組。已註冊的
``name`` 優先於 id,因為已註冊格式的 id 是動態的(``>= 0xC000``)。未辨識的格式為 ``"other"``。

執行器指令
----------

``AC_clipboard_formats``(存活,Windows)、``AC_classify_formats``(``formats``)與
``AC_diff_formats``(``before`` / ``after``)——後兩者為純函式,可在任何平台執行。皆以唯讀
``ac_*`` MCP 工具及 Script Builder 指令(位於 **Data** 分類下)形式提供。
