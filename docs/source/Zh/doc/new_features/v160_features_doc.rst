剪貼簿檔案拖放清單(CF_HDROP)
==============================

剪貼簿層原本能承載文字與影像,``rich_clipboard`` 又加入了 HTML,但框架始終無法把一份
*檔案清單*放上剪貼簿——也就是當你複製檔案後在他處 ``Ctrl+V`` 進行真正的檔案複製時,
Explorer 讀取的 ``CF_HDROP`` 內容。建構這個位元組區塊相當瑣碎:一個固定 20 位元組的
``DROPFILES`` 標頭,後接以雙重 null 結尾(預設 UTF-16)的路徑清單,且標頭的 ``pFiles``
位移需指向該清單。``clipboard_files`` 將這段容易出錯的封裝獨立出來。

封裝邏輯位於純粹、可完整單元測試的 ``build_dropfiles`` / ``parse_dropfiles`` 位元組函式
(不需裝置、任何平台皆可),其上再疊加僅限 Windows 的 ``set_clipboard_files`` /
``get_clipboard_files`` 薄包裝——與 ``rich_clipboard`` 處理 ``CF_HTML`` 的拆分方式相同。
純函式不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (build_dropfiles, parse_dropfiles,
                                 set_clipboard_files, get_clipboard_files)

    # 將兩個檔案放上剪貼簿,可貼進 Explorer(Windows)
    set_clipboard_files([r"C:\reports\q1.pdf", r"C:\reports\q2.pdf"])
    print(get_clipboard_files())

    # 位元組層完全不需剪貼簿即可測試
    blob = build_dropfiles([r"C:\a\one.txt"], point=(10, 20))
    assert parse_dropfiles(blob)["paths"] == [r"C:\a\one.txt"]

``build_dropfiles(paths, *, point=(0, 0), wide=True, non_client=False)`` 回傳原始
``DROPFILES`` 位元組;``parse_dropfiles`` 將其還原為 ``{paths, point, wide, non_client}``。
``set_clipboard_files`` / ``get_clipboard_files`` 透過 Windows 剪貼簿寫入與讀取該清單
(無檔案清單時 ``get`` 回傳 ``None``)。

執行器指令
----------

``AC_set_clipboard_files``(``paths`` → ``{set, count}``)與 ``AC_get_clipboard_files``
(→ ``{found, paths}``)。兩者以 MCP 工具 ``ac_set_clipboard_files`` /
``ac_get_clipboard_files`` 及 Script Builder 指令 **Set Clipboard Files** /
**Get Clipboard Files**(位於 **Data** 分類下)形式提供。
