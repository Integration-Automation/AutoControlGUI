將檔案拖放到視窗(WM_DROPFILES)
==============================

``clipboard_files`` 只是把檔案拖放清單*放上*剪貼簿,讓使用者可以 ``Ctrl+V``;``file_drop`` 則
主動把檔案**拖放**到目標視窗——也就是拖放動作的完成——透過送出帶有 ``DROPFILES`` 位元組區塊的
``WM_DROPFILES`` 訊息達成。它重用 ``clipboard_files.build_dropfiles`` 來打包該區塊(位元組配置
共用,不重新實作),並透過可注入的 *driver* 接縫分派,因此「打包 + 分派」邏輯可在任何平台以
假 driver 單元測試;真正的 ``GlobalAlloc`` + ``PostMessage`` 位於預設的 Win32 driver。不匯入
``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import plan_file_drop, drop_files

    # 純試跑——檢視 payload 但不送出:
    plan_file_drop(["C:\\a\\one.txt"], point=(10, 20))
    # {"message": 0x233, "paths": [...], "point": [10, 20], "wide": True,
    #  "blob_size": ...}

    # 對視窗 handle 真正拖放(Windows):
    drop_files(hwnd, ["C:\\a\\one.txt", "C:\\b\\two.png"], point=(10, 20))

    # 注入 driver 以攔截送出(例如在測試中):
    drop_files(hwnd, ["x.txt"], driver=lambda hwnd, blob, point: True)

``point`` 是視窗工作區(client area)內的拖放座標。``drop_files`` 回傳 ``bool``;預設 driver 送出
真正的 ``WM_DROPFILES``(接收視窗隨後擁有該記憶體並透過 ``DragFinish`` 釋放),在非 Windows 平台
拋出 ``RuntimeError``。

執行器指令
----------

``AC_drop_files``(``hwnd`` / ``paths`` / ``point``)執行拖放;``AC_plan_file_drop``
(``paths`` / ``point``)為純試跑。皆以對應的 ``ac_*`` MCP 工具(drop 為僅副作用、plan 為唯讀)
及 Script Builder 指令(位於 **Window** 分類下)形式提供。
