解析檔案類型已註冊的應用程式
============================

:func:`open_path`(``shell_open``)用註冊的應用程式開啟檔案;``file_assoc`` 回答相反的唯讀問題——
那個應用程式是「哪一個」?給定 ``report.pdf``(或裸的 ``.pdf`` / ``pdf``),它會透過 Windows
``AssocQueryStringW`` shell API 回傳已註冊的執行檔、友善應用程式名稱、開啟命令列與 MIME 內容類型。

* :func:`normalize_ext` ——純輔助函式,把路徑 / ``.ext`` / 裸 ``ext`` 轉成小寫的 ``.ext``,
* :func:`file_association` ——透過可注入的 ``resolver`` 接縫執行查詢(預設為真正的 shell API)。

組裝邏輯可透過可注入的 ``resolver`` 在非 Windows 上單元測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import file_association, normalize_ext

    normalize_ext("report.PDF")     # ".pdf"
    normalize_ext("archive.tar.gz") # ".gz"

    file_association("report.pdf")
    # {"ext": ".pdf", "command": "...AcroRd32.exe \"%1\"",
    #  "exe": "...AcroRd32.exe", "friendly": "Adobe Acrobat",
    #  "content_type": "application/pdf"}

當該類型未註冊任何應用程式時,應用程式欄位為 ``None``。這是 :func:`open_path` 的自然搭檔:
``file_association`` 告訴你「什麼」會開啟檔案(可斷言「PDF 用 Acrobat 開,不是瀏覽器」),而
``open_path`` 實際開啟它。即時查詢使用 Windows shell API;其他平台請傳入自己的 ``resolver``。

執行器指令
----------

``AC_normalize_ext``(``target`` → ``{ext}``,純)與 ``AC_file_association``
(``target`` → 關聯 dict)。皆以對應的 ``ac_*`` MCP 工具(皆唯讀)及 Script Builder 指令
(位於 **Shell** 分類下)形式提供。
